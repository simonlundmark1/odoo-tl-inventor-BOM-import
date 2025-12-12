from odoo import models, fields


class TlRentalBookingLineImage(models.Model):
    _inherit = 'tl.rental.booking.line'

    product_image = fields.Image(
        string="Image",
        related='product_id.image_128',
        store=False,
    )
