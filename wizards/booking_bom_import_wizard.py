from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

from ..services.excel_parser import iter_bom_rows, aggregate_bom_rows, check_openpyxl

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
    
    file = fields.Binary(string="Excel File", required=True)
    filename = fields.Char(string="Filename")
    
    replace_existing = fields.Boolean(
        string="Replace Existing Lines",
        default=False,
        help="Remove existing booking lines before importing."
    )
    
    # Results
    result_message = fields.Html(string="Import Result", readonly=True)
    state = fields.Selection([
        ('upload', 'Upload'),
        ('confirm', 'Confirm'),
        ('done', 'Done'),
    ], default='upload')
    
    # Preview data (stored as text for simplicity)
    preview_data = fields.Text(string="Preview Data")
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
        
        import base64
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
            
            # Search by name (case-insensitive)
            product = Product.search([('name', '=ilike', part_number)], limit=1)
            
            if not product:
                # Try partial match on name
                product = Product.search([('name', 'ilike', part_number)], limit=1)
            
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
                missing.append(part_number)
        
        # Store results
        import json
        self.preview_data = json.dumps(matched)
        self.matched_count = len(matched)
        self.missing_count = len(missing)
        self.missing_products = '\n'.join(missing) if missing else ''
        
        if duplicates:
            dup_warnings = [f"• {d['part_number']}: förekommer {d['occurrences']} gånger → summerad kvantitet: {d['total_qty']}" 
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
        """Import matched products as booking lines."""
        self.ensure_one()
        
        if not self.preview_data:
            raise UserError(_("Please preview the file first."))
        
        import json
        matched = json.loads(self.preview_data)
        
        if not matched:
            raise UserError(_("No products matched. Nothing to import."))
        
        booking = self.booking_id
        
        # Optionally clear existing lines
        if self.replace_existing:
            booking.line_ids.unlink()
        
        # Create booking lines
        BookingLine = self.env['tl.rental.booking.line']
        created_lines = []
        
        for item in matched:
            vals = {
                'booking_id': booking.id,
                'product_id': item['product_id'],
                'quantity': item['quantity'],
            }
            # source_warehouse_id will be set by create() from booking header
            line = BookingLine.create(vals)
            created_lines.append(line)
        
        # Build result message
        msg_parts = [
            f"<p><strong>✅ Import complete!</strong></p>",
            f"<p>Created {len(created_lines)} booking lines.</p>",
        ]
        
        if self.missing_count > 0:
            msg_parts.append(f"<p><strong>⚠️ {self.missing_count} products not found</strong> (see list below)</p>")
            missing_list = self.missing_products.replace('\n', '<br/>')
            msg_parts.append(f"<p style='color: #856404; background: #fff3cd; padding: 8px; border-radius: 4px;'>{missing_list}</p>")
        
        if self.duplicates_warning:
            msg_parts.append(f"<p><strong>ℹ️ Duplicates were aggregated:</strong></p>")
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
