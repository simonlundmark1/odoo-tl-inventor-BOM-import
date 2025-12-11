from odoo import models, fields, api


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    tlrm_rental_location_id = fields.Many2one(
        'stock.location',
        string="TL Rental Out Location",
        check_company=True,
        help="Location where products are moved when rented out. "
             "Products in this location are not available for other bookings.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        for warehouse in warehouses:
            warehouse._create_tlrm_rental_location()
        return warehouses

    def _create_tlrm_rental_location(self):
        """Create the TL Rental Out location for this warehouse if it doesn't exist."""
        self.ensure_one()
        if self.tlrm_rental_location_id:
            return self.tlrm_rental_location_id

        Location = self.env['stock.location']
        
        # Create as child of the warehouse's view location
        parent_location = self.view_location_id
        if not parent_location:
            return False

        rental_location = Location.create({
            'name': 'TL Rental Out',
            'usage': 'internal',  # Internal so we can track stock there
            'location_id': parent_location.id,
            'company_id': self.company_id.id,
        })
        self.tlrm_rental_location_id = rental_location
        return rental_location

    @api.model
    def _create_tlrm_rental_locations_for_existing(self):
        """Create TL Rental Out locations for all existing warehouses.
        
        Called from data file during module installation/upgrade.
        """
        warehouses = self.search([('tlrm_rental_location_id', '=', False)])
        for warehouse in warehouses:
            warehouse._create_tlrm_rental_location()

    @api.model
    def _fix_tlrm_rental_location_usage(self):
        """Fix existing TL Rental Out locations to use 'internal' usage.
        
        Called during module upgrade to fix locations that were created
        with 'customer' usage.
        """
        locations = self.env['stock.location'].search([
            ('name', '=', 'TL Rental Out'),
            ('usage', '=', 'customer'),
        ])
        if locations:
            locations.write({'usage': 'internal'})
