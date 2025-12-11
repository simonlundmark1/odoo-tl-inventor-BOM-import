from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from odoo import fields
from datetime import timedelta


@tagged('post_install', '-at_install')
class TestRentalAvailability(TransactionCase):
    """Test rental booking availability logic.
    
    Business rules (optimistic booking):
    - Fleet capacity is the base for availability (not physical stock)
    - 'reserved' state is a soft hold - does NOT block availability
    - 'booked' state is a hard lock - blocks availability
    - 'ongoing' and 'finished' states also block availability
    - Availability check happens at action_book(), not action_confirm()
    """

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
        
        # Create product with fleet capacity (not stock.quant based)
        cls.product = cls.env['product.product'].create({
            'name': 'Test Rental Product',
            'type': 'product',
            'default_code': 'TEST-RENTAL',
        })
        # Set fleet capacity on the template
        cls.product.product_tmpl_id.tlrm_fleet_capacity = 20.0
        
        cls.project = cls.env['project.project'].create({
            'name': 'Test Project',
            'company_id': cls.company.id,
        })

    def _create_booking(self, product, qty, date_start, date_end, state='draft'):
        """Helper to create a booking with one line.
        
        :param state: Target state - 'draft', 'reserved', or 'booked'
        """
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
        if state in ('reserved', 'booked'):
            booking.action_confirm()  # draft -> reserved
        if state == 'booked':
            booking.action_book()  # reserved -> booked (hard lock)
        return booking

    def test_01_confirm_creates_soft_reservation(self):
        """Test that action_confirm creates a soft reservation (no availability check)."""
        date_start = fields.Datetime.now() + timedelta(days=10)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 10, date_start, date_end, state='reserved'
        )
        
        self.assertEqual(booking.state, 'reserved')

    def test_02_book_within_capacity_succeeds(self):
        """Test that action_book within fleet capacity succeeds."""
        date_start = fields.Datetime.now() + timedelta(days=20)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 20, date_start, date_end, state='booked'
        )
        
        self.assertEqual(booking.state, 'booked')

    def test_03_book_over_capacity_fails(self):
        """Test that action_book over fleet capacity fails."""
        date_start = fields.Datetime.now() + timedelta(days=30)
        date_end = date_start + timedelta(days=5)
        
        # Create and confirm (soft reservation - no check)
        booking = self._create_booking(
            self.product, 25, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking.state, 'reserved')
        
        # Lock booking (hard commitment - availability check)
        with self.assertRaises(ValidationError) as cm:
            booking.action_book()
        
        self.assertIn('Not enough availability', str(cm.exception))

    def test_04_reserved_does_not_block_availability(self):
        """Test that 'reserved' state does NOT block availability (optimistic booking)."""
        date_start = fields.Datetime.now() + timedelta(days=40)
        date_end = date_start + timedelta(days=5)
        
        # First booking: reserved (soft hold)
        booking1 = self._create_booking(
            self.product, 15, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking1.state, 'reserved')
        
        # Second booking: can also be reserved for same period (overbooking allowed at reserved)
        booking2 = self._create_booking(
            self.product, 15, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')
        
        # First booking can be locked (15 <= 20 capacity)
        booking1.action_book()
        self.assertEqual(booking1.state, 'booked')
        
        # Second booking cannot be locked (15 + 15 > 20 capacity)
        with self.assertRaises(ValidationError):
            booking2.action_book()

    def test_05_booked_state_blocks_availability(self):
        """Test that 'booked' state blocks availability for overlapping bookings."""
        date_start = fields.Datetime.now() + timedelta(days=50)
        date_end = date_start + timedelta(days=5)
        
        # First booking: booked (hard lock)
        booking1 = self._create_booking(
            self.product, 15, date_start, date_end, state='booked'
        )
        self.assertEqual(booking1.state, 'booked')
        
        # Second booking: can reserve but not book if it exceeds capacity
        booking2 = self._create_booking(
            self.product, 10, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')
        
        # 15 + 10 > 20, so booking should fail
        with self.assertRaises(ValidationError):
            booking2.action_book()

    def test_06_non_overlapping_bookings_independent(self):
        """Test that non-overlapping bookings don't affect each other."""
        date_start1 = fields.Datetime.now() + timedelta(days=60)
        date_end1 = date_start1 + timedelta(days=5)
        
        date_start2 = date_end1 + timedelta(days=1)
        date_end2 = date_start2 + timedelta(days=5)
        
        # Both can be booked at full capacity since they don't overlap
        booking1 = self._create_booking(
            self.product, 20, date_start1, date_end1, state='booked'
        )
        self.assertEqual(booking1.state, 'booked')
        
        booking2 = self._create_booking(
            self.product, 20, date_start2, date_end2, state='booked'
        )
        self.assertEqual(booking2.state, 'booked')

    def test_07_availability_grid_returns_data(self):
        """Test that get_availability_grid returns proper structure."""
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=fields.Datetime.now(),
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
        self.assertEqual(result['rows'][0]['fleet_capacity'], 20.0)

    def test_08_booked_state_shows_committed_in_grid(self):
        """Test that 'booked' state shows as committed in availability grid."""
        date_start = fields.Datetime.now() + timedelta(days=70)
        date_end = date_start + timedelta(days=7)
        
        booking = self._create_booking(
            self.product, 15, date_start, date_end, state='booked'
        )
        self.assertEqual(booking.state, 'booked')
        
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=date_start,
            week_count=2,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        first_week_cell = result['rows'][0]['cells'][0]
        self.assertEqual(first_week_cell['committed'], 15.0)
        self.assertEqual(first_week_cell['available'], 5.0)  # 20 - 15 = 5

    def test_09_reserved_state_not_in_committed(self):
        """Test that 'reserved' state does NOT show in committed (optimistic)."""
        date_start = fields.Datetime.now() + timedelta(days=80)
        date_end = date_start + timedelta(days=7)
        
        booking = self._create_booking(
            self.product, 15, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking.state, 'reserved')
        
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=date_start,
            week_count=2,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        first_week_cell = result['rows'][0]['cells'][0]
        # Reserved does NOT count as committed in optimistic mode
        self.assertEqual(first_week_cell['committed'], 0.0)
        self.assertEqual(first_week_cell['available'], 20.0)  # Full capacity available

    def test_10_no_fleet_capacity_fails_booking(self):
        """Test that booking fails if fleet capacity is not set."""
        # Create product without fleet capacity
        product_no_capacity = self.env['product.product'].create({
            'name': 'No Capacity Product',
            'type': 'product',
        })
        # Fleet capacity defaults to 0
        
        date_start = fields.Datetime.now() + timedelta(days=90)
        date_end = date_start + timedelta(days=5)
        
        booking = self.env['tl.rental.booking'].create({
            'project_id': self.project.id,
            'source_warehouse_id': self.warehouse.id,
            'date_start': date_start,
            'date_end': date_end,
            'line_ids': [(0, 0, {
                'product_id': product_no_capacity.id,
                'quantity': 1,
            })],
        })
        booking.action_confirm()
        
        with self.assertRaises(ValidationError) as cm:
            booking.action_book()
        
        self.assertIn('No fleet capacity configured', str(cm.exception))
