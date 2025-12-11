from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestRentalAvailability(TransactionCase):
    """Test rental booking availability logic."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        cls.company = cls.env.company
        
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id)
        ], limit=1)
        
        if not cls.warehouse:
            cls.warehouse = cls.env['stock.warehouse'].create({
                'name': 'Test Warehouse',
                'code': 'TWH',
                'company_id': cls.company.id,
            })
        
        cls.product = cls.env['product.product'].create({
            'name': 'Test Rental Product',
            'type': 'product',
            'default_code': 'TEST-RENTAL',
        })
        
        cls.project = cls.env['project.project'].create({
            'name': 'Test Project',
            'company_id': cls.company.id,
        })
        
        cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': cls.warehouse.lot_stock_id.id,
            'quantity': 20.0,
        })

    def _create_booking(self, product, qty, date_start, date_end, confirm=False):
        """Helper to create a booking with one line."""
        booking = self.env['tl.rental.booking'].create({
            'project_id': self.project.id,
            'source_warehouse_id': self.warehouse.id,
            'date_start': date_start,
            'date_end': date_end,
            'line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': qty,
            })],
        })
        if confirm:
            booking.action_confirm()
        return booking

    def test_01_basic_availability_check(self):
        """Test that booking within capacity succeeds."""
        date_start = datetime.now() + timedelta(days=10)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 10, date_start, date_end, confirm=True
        )
        
        self.assertEqual(booking.state, 'reserved')

    def test_02_exact_capacity_succeeds(self):
        """Test that booking exactly at capacity succeeds."""
        date_start = datetime.now() + timedelta(days=20)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 20, date_start, date_end, confirm=True
        )
        
        self.assertEqual(booking.state, 'reserved')

    def test_03_over_capacity_fails(self):
        """Test that booking over capacity fails."""
        date_start = datetime.now() + timedelta(days=30)
        date_end = date_start + timedelta(days=5)
        
        with self.assertRaises(ValidationError) as cm:
            self._create_booking(
                self.product, 25, date_start, date_end, confirm=True
            )
        
        self.assertIn('Not enough availability', str(cm.exception))

    def test_04_overlapping_bookings_sum_correctly(self):
        """Test that overlapping bookings are summed for availability."""
        date_start = datetime.now() + timedelta(days=40)
        date_end = date_start + timedelta(days=5)
        
        booking1 = self._create_booking(
            self.product, 10, date_start, date_end, confirm=True
        )
        self.assertEqual(booking1.state, 'reserved')
        
        booking2 = self._create_booking(
            self.product, 10, date_start, date_end, confirm=True
        )
        self.assertEqual(booking2.state, 'reserved')
        
        with self.assertRaises(ValidationError):
            self._create_booking(
                self.product, 1, date_start, date_end, confirm=True
            )

    def test_05_non_overlapping_bookings_independent(self):
        """Test that non-overlapping bookings don't affect each other."""
        date_start1 = datetime.now() + timedelta(days=50)
        date_end1 = date_start1 + timedelta(days=5)
        
        date_start2 = date_end1 + timedelta(days=1)
        date_end2 = date_start2 + timedelta(days=5)
        
        booking1 = self._create_booking(
            self.product, 20, date_start1, date_end1, confirm=True
        )
        self.assertEqual(booking1.state, 'reserved')
        
        booking2 = self._create_booking(
            self.product, 20, date_start2, date_end2, confirm=True
        )
        self.assertEqual(booking2.state, 'reserved')

    def test_06_availability_grid_returns_data(self):
        """Test that get_availability_grid returns proper structure."""
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=datetime.now(),
            week_count=4,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        self.assertIn('meta', result)
        self.assertIn('columns', result)
        self.assertIn('rows', result)
        self.assertEqual(len(result['columns']), 4)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['product_id'], self.product.id)

    def test_07_reserved_state_blocks_availability(self):
        """Test that 'reserved' state bookings reduce availability in grid."""
        date_start = datetime.now() + timedelta(days=60)
        date_end = date_start + timedelta(days=7)
        
        booking = self._create_booking(
            self.product, 15, date_start, date_end, confirm=True
        )
        
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=date_start,
            week_count=2,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        first_week_cell = result['rows'][0]['cells'][0]
        self.assertEqual(first_week_cell['booked'], 15.0)
        self.assertEqual(first_week_cell['available'], 5.0)
