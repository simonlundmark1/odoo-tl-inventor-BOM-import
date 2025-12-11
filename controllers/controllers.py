from odoo import http
from odoo.http import request


def _to_int(value):
    """Safely convert value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TlrmAvailabilityController(http.Controller):

    @http.route(
        '/tlrm/availability_grid/global',
        type='json',
        auth='user'
    )
    def tlrm_availability_global(
        self,
        company_id=None,
        warehouse_id=None,
        date_start=None,
        week_count=12,
        product_domain=None,
    ):
        env = request.env

        company_id = _to_int(company_id)
        company = env['res.company'].browse(company_id) if company_id else env.company

        line_model = env['tl.rental.booking.line'].with_context(
            allowed_company_ids=[company.id]
        )

        week_count = _to_int(week_count) or 12
        warehouse_id = _to_int(warehouse_id)

        if not product_domain:
            product_domain = [('type', '=', 'product')]

        products = env['product.product'].search(product_domain)
        product_ids = products.ids

        grid = line_model.get_availability_grid(
            product_ids=product_ids,
            date_start=date_start,
            week_count=week_count,
            warehouse_id=warehouse_id,
            company_id=company.id,
            needed_by_product=None,
        )

        grid.setdefault('meta', {})
        grid['meta'].setdefault('mode', 'global')
        return grid

    @http.route(
        '/tlrm/availability_grid/booking',
        type='json',
        auth='user'
    )
    def tlrm_availability_booking(
        self,
        booking_id,
        week_count=12,
        anchor='booking_period',
        date_start=None,
        warehouse_id=None,
    ):
        env = request.env

        booking_id = _to_int(booking_id)
        if not booking_id:
            return {'error': 'invalid_booking_id'}

        booking = env['tl.rental.booking'].browse(booking_id)
        if not booking.exists():
            return {'error': 'booking_not_found'}

        company = booking.company_id
        line_model = env['tl.rental.booking.line'].with_context(
            allowed_company_ids=[company.id]
        )

        week_count = _to_int(week_count) or 12
        warehouse_id = _to_int(warehouse_id)

        if not warehouse_id:
            warehouse_id = booking.source_warehouse_id.id or None

        if anchor == 'booking_period' and not date_start:
            date_start = booking.date_start or booking.date_end

        needed_by_product = {}
        product_ids = []
        for line in booking.line_ids:
            if not line.product_id:
                continue
            pid = line.product_id.id
            qty = line.quantity or 0.0
            if pid not in needed_by_product:
                needed_by_product[pid] = 0.0
                product_ids.append(pid)
            needed_by_product[pid] += qty

        grid = line_model.get_availability_grid(
            product_ids=product_ids,
            date_start=date_start,
            week_count=week_count,
            warehouse_id=warehouse_id,
            company_id=company.id,
            needed_by_product=needed_by_product,
        )

        grid_meta = grid.setdefault('meta', {})
        grid_meta['mode'] = 'booking'
        grid_meta['booking_id'] = booking.id
        return grid

    @http.route(
        '/tlrm/warehouses',
        type='json',
        auth='user'
    )
    def tlrm_get_warehouses(self, company_id=None):
        """Get list of warehouses for the filter dropdown."""
        env = request.env
        
        company_id = _to_int(company_id)
        company = env['res.company'].browse(company_id) if company_id else env.company
        
        warehouses = env['stock.warehouse'].search([
            ('company_id', '=', company.id)
        ])
        
        return {
            'warehouses': [
                {'id': wh.id, 'name': wh.name}
                for wh in warehouses
            ]
        }
