from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

from ..services.excel_parser import iter_bom_rows, aggregate_bom_rows, check_openpyxl

_logger = logging.getLogger(__name__)


class ProductImportWizard(models.TransientModel):
    _name = 'tl.inventor.product.import.wizard'
    _description = 'Import Products from Inventor BOM'

    file = fields.Binary(string="Excel File", required=True)
    filename = fields.Char(string="Filename")
    
    create_missing = fields.Boolean(
        string="Create Missing Products",
        default=True,
        help="Create new products for part numbers not found in the system."
    )
    update_existing = fields.Boolean(
        string="Update Existing Products",
        default=False,
        help="Update weight and description of existing products."
    )
    match_field = fields.Selection([
        ('name', 'Product Name'),
        ('default_code', 'Internal Reference'),
    ], string="Match Products By", default='name', required=True)
    
    default_category_id = fields.Many2one(
        'product.category',
        string="Default Category",
        help="Category for newly created products."
    )
    
    # Results (shown after import)
    result_message = fields.Html(string="Import Result", readonly=True)
    state = fields.Selection([
        ('upload', 'Upload'),
        ('done', 'Done'),
    ], default='upload')

    def action_import(self):
        """Import products from the uploaded Excel file."""
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
        
        # Prepare results tracking
        created = []
        updated = []
        skipped = []
        errors = []
        
        ProductTemplate = self.env['product.template']
        
        for row in aggregated_rows:
            part_number = row['part_number']
            
            try:
                # Search for existing product
                domain = [(self.match_field, '=ilike', part_number)]
                product = ProductTemplate.search(domain, limit=1)
                
                if product:
                    if self.update_existing:
                        vals = {}
                        if row['weight_kg']:
                            vals['weight'] = row['weight_kg']
                        if row['description']:
                            vals['description'] = row['description']
                        if row['image_base64']:
                            vals['image_1920'] = row['image_base64']
                        if vals:
                            product.write(vals)
                            updated.append(part_number)
                        else:
                            skipped.append(part_number)
                    else:
                        skipped.append(part_number)
                else:
                    if self.create_missing:
                        vals = {
                            'name': part_number,
                            'type': 'product',
                            'weight': row['weight_kg'] or 0.0,
                        }
                        if row['description']:
                            vals['description'] = row['description']
                        if row['image_base64']:
                            vals['image_1920'] = row['image_base64']
                        if self.default_category_id:
                            vals['categ_id'] = self.default_category_id.id
                        
                        ProductTemplate.create(vals)
                        created.append(part_number)
                    else:
                        skipped.append(part_number)
                        
            except Exception as e:
                _logger.exception(f"Error importing {part_number}")
                errors.append(f"{part_number}: {str(e)}")
        
        # Build result message
        msg_parts = []
        
        if duplicates:
            dup_list = ', '.join([f"{d['part_number']} (x{d['occurrences']}→{d['total_qty']})" for d in duplicates[:5]])
            if len(duplicates) > 5:
                dup_list += f" ... and {len(duplicates) - 5} more"
            msg_parts.append(f"<p><strong>⚠️ Duplicates aggregated:</strong> {dup_list}</p>")
        
        if created:
            msg_parts.append(f"<p><strong>✅ Created:</strong> {len(created)} products</p>")
        if updated:
            msg_parts.append(f"<p><strong>🔄 Updated:</strong> {len(updated)} products</p>")
        if skipped:
            msg_parts.append(f"<p><strong>⏭️ Skipped:</strong> {len(skipped)} products</p>")
        if errors:
            error_list = '<br/>'.join(errors[:10])
            if len(errors) > 10:
                error_list += f"<br/>... and {len(errors) - 10} more errors"
            msg_parts.append(f"<p><strong>❌ Errors:</strong><br/>{error_list}</p>")
        
        self.result_message = ''.join(msg_parts) or "<p>No changes made.</p>"
        self.state = 'done'
        
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
