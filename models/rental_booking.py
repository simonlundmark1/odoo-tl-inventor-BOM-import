from odoo import models, api


class TlRentalBookingBomImport(models.Model):
    _inherit = 'tl.rental.booking'

    def action_open_bom_import_wizard(self):
        """Open the BOM import wizard for this booking."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import BOM',
            'res_model': 'tl.inventor.booking.bom.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_booking_id': self.id,
            },
        }
