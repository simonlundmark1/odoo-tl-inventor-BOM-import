from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import json
import logging

from ..services.excel_parser import aggregate_bom_rows, check_openpyxl

_logger = logging.getLogger(__name__)


class BookingBomImportWizard(models.TransientModel):
    _name = 'tl.inventor.booking.bom.import.wizard'
    _description = 'Import BOM to Booking Lines'

    booking_id = fields.Many2one(
        'tl.rental.booking',
        string="Booking",
        required=True,
        ondelete='cascade',
    )
    
    file = fields.Binary(string="Excel File", attachment=False)
    filename = fields.Char(string="Filename")
    
    replace_existing = fields.Boolean(
        string="Replace Existing Lines",
        default=False,
        help="Remove existing booking lines before importing."
    )
    
    create_missing_products = fields.Boolean(
        string="Create Missing Products",
        default=False,
        help="Create new products for items not found in the database."
    )
    
    # Results
    result_message = fields.Html(string="Import Result", readonly=True)
    state = fields.Selection([
        ('upload', 'Upload'),
        ('confirm', 'Confirm'),
        ('done', 'Done'),
    ], default='upload')
    
    # Preview data (stored as JSON)
    preview_data = fields.Text(string="Preview Data")
    missing_data = fields.Text(string="Missing Products Data")
    matched_count = fields.Integer(string="Matched Products")
    missing_count = fields.Integer(string="Missing Products")
    missing_products = fields.Text(string="Missing Products List")
    duplicates_warning = fields.Text(string="Duplicates Warning")

    def action_preview(self):
        """Parse the file and show a preview before importing."""
        self.ensure_one()
        
        try:
            check_openpyxl()
        except ImportError as e:
            raise UserError(str(e))
        
        if not self.file:
            raise UserError(_("Please upload an Excel file."))
        
        file_content = base64.b64decode(self.file)
        
        # Parse and aggregate rows
        aggregated_rows, duplicates = aggregate_bom_rows(file_content, self.filename)
        
        if not aggregated_rows:
            raise UserError(_("No valid rows found in the Excel file."))
        
        # Match against existing products
        Product = self.env['product.product']
        matched = []
        missing = []
        
        for row in aggregated_rows:
            part_number = row['part_number']
            
            # Search by name (case-insensitive exact match first)
            product = Product.search([('name', '=ilike', part_number)], limit=1)
            
            if not product:
                # Try by default_code
                product = Product.search([('default_code', '=ilike', part_number)], limit=1)
            
            if product:
                matched.append({
                    'part_number': part_number,
                    'product_id': product.id,
                    'product_name': product.display_name,
                    'quantity': row['quantity'],
                })
            else:
                missing.append({
                    'part_number': part_number,
                    'quantity': row['quantity'],
                    'description': row.get('description', ''),
                    'weight_kg': row.get('weight_kg', 0),
                    'image_base64': row.get('image_base64', False),
                })
        
        # Store results
        self.preview_data = json.dumps(matched)
        self.missing_data = json.dumps(missing)
        self.matched_count = len(matched)
        self.missing_count = len(missing)
        self.missing_products = '\n'.join([m['part_number'] for m in missing]) if missing else ''
        
        if duplicates:
            dup_warnings = [f"• {d['part_number']}: {d['occurrences']}x → total: {d['total_qty']}" 
                          for d in duplicates]
            self.duplicates_warning = '\n'.join(dup_warnings)
        else:
            self.duplicates_warning = ''
        
        self.state = 'confirm'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        """Import matched products as booking lines, optionally creating missing products."""
        self.ensure_one()
        
        if not self.preview_data:
            raise UserError(_("Please preview the file first."))
        
        matched = json.loads(self.preview_data)
        missing = json.loads(self.missing_data) if self.missing_data else []
        
        booking = self.booking_id
        
        # Optionally clear existing lines
        if self.replace_existing:
            booking.line_ids.unlink()
        
        BookingLine = self.env['tl.rental.booking.line']
        ProductTemplate = self.env['product.template']
        created_lines = []
        created_products = []
        
        # Create booking lines for matched products
        for item in matched:
            line = BookingLine.create({
                'booking_id': booking.id,
                'product_id': item['product_id'],
                'quantity': item['quantity'],
            })
            created_lines.append(line)
        
        # Handle missing products
        if self.create_missing_products and missing:
            for item in missing:
                # Create product template (Odoo 19: type='consu' + is_storable=True for storable)
                product_vals = {
                    'name': item['part_number'],
                    'is_storable': True,
                    'weight': item.get('weight_kg', 0),
                    'description': item.get('description', ''),
                }
                if item.get('image_base64'):
                    product_vals['image_1920'] = item['image_base64']
                
                template = ProductTemplate.create(product_vals)
                product = template.product_variant_id
                created_products.append(template)
                
                # Create booking line for the new product
                line = BookingLine.create({
                    'booking_id': booking.id,
                    'product_id': product.id,
                    'quantity': item['quantity'],
                })
                created_lines.append(line)
        
        # Build result message
        msg_parts = [f"<p><strong>✅ Import klar!</strong></p>"]
        msg_parts.append(f"<p>Skapade <strong>{len(created_lines)}</strong> booking-rader.</p>")
        
        if created_products:
            msg_parts.append(f"<p>Skapade <strong>{len(created_products)}</strong> nya produkter:</p>")
            product_names = [p.name for p in created_products]
            msg_parts.append(f"<ul>{''.join(f'<li>{n}</li>' for n in product_names)}</ul>")
        
        skipped = len(missing) - len(created_products) if missing else 0
        if skipped > 0:
            msg_parts.append(f"<p><strong>⚠️ {skipped} produkter hoppades över</strong> (fanns ej, skapades ej)</p>")
        
        if self.duplicates_warning:
            msg_parts.append(f"<p><strong>ℹ️ Dubbletter summerades:</strong></p>")
            dup_list = self.duplicates_warning.replace('\n', '<br/>')
            msg_parts.append(f"<p style='color: #0c5460; background: #d1ecf1; padding: 8px; border-radius: 4px;'>{dup_list}</p>")
        
        self.result_message = ''.join(msg_parts)
        self.state = 'done'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back(self):
        """Go back to upload state."""
        self.state = 'upload'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}
