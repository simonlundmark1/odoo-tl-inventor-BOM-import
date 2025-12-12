from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from odoo import fields
from datetime import timedelta


@tagged('post_install', '-at_install')
class TestRentalAvailability(TransactionCase):
    """Test rental booking availability logic.
    
    Business rules:
    - Fleet capacity is auto-computed from stock.quant across all warehouses
    - 'reserved' state blocks availability for planning (no stock movements)
    - 'booked' state is a hard lock with stock movements (pickings created)
    - 'ongoing' and 'finished' states also block availability
    - Availability check happens at action_confirm() for planning
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
        
        # Create product - fleet capacity is auto-computed from stock.quant
        cls.product = cls.env['product.product'].create({
            'name': 'Test Rental Product',
            'type': 'consu',
            'default_code': 'TEST-RENTAL',
        })
        # Create stock.quant to set fleet capacity (20 units)
        cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': cls.warehouse.lot_stock_id.id,
            'quantity': 20.0,
        })
        
        cls.project = cls.env['project.project'].create({
            'name': 'Test Project',
            'company_id': cls.company.id,
        })

    def _create_booking(self, product, qty, date_start, date_end, state='draft'):
        """Helper to create a booking with one line.
        
        :param state: Target state - 'draft', 'planned', or 'reserved'
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
        if state in ('planned', 'reserved'):
            booking.action_confirm()  # draft -> planned
        if state == 'reserved':
            booking.action_reserve()  # planned -> reserved (hard lock)
        return booking

    def test_01_confirm_creates_planned_booking(self):
        """Test that action_confirm creates a planned booking."""
        date_start = fields.Datetime.now() + timedelta(days=10)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 10, date_start, date_end, state='planned'
        )
        
        self.assertEqual(booking.state, 'planned')

    def test_02_reserve_within_capacity_succeeds(self):
        """Test that action_reserve within fleet capacity succeeds."""
        date_start = fields.Datetime.now() + timedelta(days=20)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 20, date_start, date_end, state='reserved'
        )
        
        self.assertEqual(booking.state, 'reserved')

    def test_03_plan_over_capacity_fails(self):
        """Test that planning over fleet capacity fails."""
        date_start = fields.Datetime.now() + timedelta(days=30)
        date_end = date_start + timedelta(days=5)
        
        # Trying to plan 25 units when only 20 available should fail
        with self.assertRaises(ValidationError) as cm:
            self._create_booking(
                self.product, 25, date_start, date_end, state='planned'
            )
        
        self.assertIn('Not enough availability', str(cm.exception))

    def test_04_planned_blocks_availability(self):
        """Test that 'planned' state blocks availability for planning."""
        date_start = fields.Datetime.now() + timedelta(days=40)
        date_end = date_start + timedelta(days=5)
        
        # First booking: planned (blocks for planning)
        booking1 = self._create_booking(
            self.product, 15, date_start, date_end, state='planned'
        )
        self.assertEqual(booking1.state, 'planned')
        
        # Second booking: can plan up to remaining capacity (20 - 15 = 5)
        booking2 = self._create_booking(
            self.product, 5, date_start, date_end, state='planned'
        )
        self.assertEqual(booking2.state, 'planned')
        
        # Third booking: trying to plan 1 more should fail (15 + 5 + 1 > 20)
        with self.assertRaises(ValidationError):
            self._create_booking(
                self.product, 1, date_start, date_end, state='reserved'
            )

    def test_05_planned_and_reserved_both_block(self):
        """Test that both planned and reserved states block availability."""
        date_start = fields.Datetime.now() + timedelta(days=50)
        date_end = date_start + timedelta(days=5)
        
        # First booking: reserved (10 units)
        booking1 = self._create_booking(
            self.product, 10, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking1.state, 'reserved')
        
        # Second booking: planned (5 units) - should work (10 + 5 = 15 <= 20)
        booking2 = self._create_booking(
            self.product, 5, date_start, date_end, state='planned'
        )
        self.assertEqual(booking2.state, 'planned')
        
        # Third booking: trying to plan 6 more should fail (10 + 5 + 6 > 20)
        with self.assertRaises(ValidationError):
            self._create_booking(
                self.product, 6, date_start, date_end, state='planned'
            )

    def test_06_non_overlapping_bookings_independent(self):
        """Test that non-overlapping bookings don't affect each other."""
        date_start1 = fields.Datetime.now() + timedelta(days=60)
        date_end1 = date_start1 + timedelta(days=5)
        
        date_start2 = date_end1 + timedelta(days=1)
        date_end2 = date_start2 + timedelta(days=5)
        
        # Both can be reserved at full capacity since they don't overlap
        booking1 = self._create_booking(
            self.product, 20, date_start1, date_end1, state='reserved'
        )
        self.assertEqual(booking1.state, 'reserved')
        
        booking2 = self._create_booking(
            self.product, 20, date_start2, date_end2, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')

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

    def test_08_reserved_state_shows_committed_in_grid(self):
        """Test that 'reserved' state shows as committed in availability grid."""
        date_start = fields.Datetime.now() + timedelta(days=70)
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
        self.assertEqual(first_week_cell['committed'], 15.0)
        self.assertEqual(first_week_cell['available'], 5.0)  # 20 - 15 = 5

    def test_09_planned_state_shows_in_committed(self):
        """Test that 'planned' state shows in committed for planning."""
        date_start = fields.Datetime.now() + timedelta(days=80)
        date_end = date_start + timedelta(days=7)
        
        booking = self._create_booking(
            self.product, 15, date_start, date_end, state='planned'
        )
        self.assertEqual(booking.state, 'planned')
        
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id],
            date_start=date_start,
            week_count=2,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        first_week_cell = result['rows'][0]['cells'][0]
        # Reserved counts as committed for planning purposes
        self.assertEqual(first_week_cell['committed'], 15.0)
        self.assertEqual(first_week_cell['available'], 5.0)  # 20 - 15 = 5

    def test_10_no_fleet_capacity_fails_booking(self):
        """Test that booking fails if fleet capacity is not set."""
        # Create product without fleet capacity
        product_no_capacity = self.env['product.product'].create({
            'name': 'No Capacity Product',
            'type': 'consu',
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
            booking.action_reserve()
        
        self.assertIn('No fleet capacity configured', str(cm.exception))

    def test_11_incoming_returns_add_to_availability(self):
        """Test that incoming returns increase availability for future bookings."""
        date_start1 = fields.Datetime.now() + timedelta(days=100)
        date_end1 = date_start1 + timedelta(days=5)
        
        # First booking uses 15 units, reserved and ongoing
        booking1 = self._create_booking(
            self.product, 15, date_start1, date_end1, state='reserved'
        )
        booking1.action_mark_ongoing()
        self.assertEqual(booking1.state, 'ongoing')
        
        # Second booking wants 10 units in period after first returns
        date_start2 = date_end1 + timedelta(days=1)  # After first booking ends
        date_end2 = date_start2 + timedelta(days=5)
        
        # With fleet=20, and 15 ongoing but returning before date_start2,
        # we should have capacity for 10 more units
        booking2 = self._create_booking(
            self.product, 10, date_start2, date_end2, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')

    def test_12_state_transitions_ongoing_finished_returned(self):
        """Test full state machine: planned -> reserved -> ongoing -> finished -> returned."""
        date_start = fields.Datetime.now() + timedelta(days=110)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 10, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking.state, 'reserved')
        
        # reserved -> ongoing
        booking.action_mark_ongoing()
        self.assertEqual(booking.state, 'ongoing')
        
        # ongoing -> finished
        booking.action_finish()
        self.assertEqual(booking.state, 'finished')
        
        # finished -> returned
        booking.action_return()
        self.assertEqual(booking.state, 'returned')

    def test_13_wrong_state_transitions_fail(self):
        """Test that invalid state transitions raise errors."""
        date_start = fields.Datetime.now() + timedelta(days=120)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 5, date_start, date_end, state='planned'
        )
        
        # Cannot mark ongoing from planned (must be reserved first)
        with self.assertRaises(ValidationError):
            booking.action_mark_ongoing()
        
        # Cannot finish from planned
        with self.assertRaises(ValidationError):
            booking.action_finish()
        
        # Cannot return from planned
        with self.assertRaises(ValidationError):
            booking.action_return()

    def test_14_validation_missing_dates(self):
        """Test that confirming without dates raises validation error."""
        booking = self.env['tl.rental.booking'].create({
            'project_id': self.project.id,
            'source_warehouse_id': self.warehouse.id,
            'date_start': False,
            'date_end': False,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 5,
            })],
        })
        
        with self.assertRaises(ValidationError) as cm:
            booking.action_confirm()
        self.assertIn('Start date is required', str(cm.exception))

    def test_15_validation_start_after_end(self):
        """Test that start date after end date raises validation error."""
        date_start = fields.Datetime.now() + timedelta(days=130)
        date_end = date_start - timedelta(days=5)  # End before start
        
        booking = self.env['tl.rental.booking'].create({
            'project_id': self.project.id,
            'source_warehouse_id': self.warehouse.id,
            'date_start': date_start,
            'date_end': date_end,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 5,
            })],
        })
        
        with self.assertRaises(ValidationError) as cm:
            booking.action_confirm()
        self.assertIn('Start date cannot be after end date', str(cm.exception))

    def test_16_cancel_booking(self):
        """Test that booking can be cancelled and cancelled bookings don't block availability."""
        date_start = fields.Datetime.now() + timedelta(days=140)
        date_end = date_start + timedelta(days=5)
        
        # Create and reserve full capacity
        booking1 = self._create_booking(
            self.product, 20, date_start, date_end, state='planned'
        )
        self.assertEqual(booking1.state, 'planned')
        
        # Cancel it
        booking1.action_cancel()
        self.assertEqual(booking1.state, 'cancelled')
        
        # Now another booking should be able to use the capacity
        booking2 = self._create_booking(
            self.product, 20, date_start, date_end, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')

    def test_17_ongoing_and_finished_block_availability(self):
        """Test that ongoing and finished states block availability."""
        date_start = fields.Datetime.now() + timedelta(days=150)
        date_end = date_start + timedelta(days=5)
        
        # First booking: ongoing (15 units)
        booking1 = self._create_booking(
            self.product, 15, date_start, date_end, state='reserved'
        )
        booking1.action_mark_ongoing()
        self.assertEqual(booking1.state, 'ongoing')
        
        # Second booking: try to plan 10 more (15 + 10 > 20)
        with self.assertRaises(ValidationError):
            self._create_booking(
                self.product, 10, date_start, date_end, state='planned'
            )

    def test_18_boundary_dates_overlap(self):
        """Test boundary case: booking ending exactly when another starts."""
        date_start1 = fields.Datetime.now() + timedelta(days=160)
        date_end1 = date_start1 + timedelta(days=5)
        
        # Second booking starts exactly when first ends
        date_start2 = date_end1
        date_end2 = date_start2 + timedelta(days=5)
        
        # Both should be reservable at full capacity (no overlap)
        booking1 = self._create_booking(
            self.product, 20, date_start1, date_end1, state='reserved'
        )
        self.assertEqual(booking1.state, 'reserved')
        
        booking2 = self._create_booking(
            self.product, 20, date_start2, date_end2, state='reserved'
        )
        self.assertEqual(booking2.state, 'reserved')

    def test_19_partial_overlap_uses_peak_committed(self):
        """Test that partial overlaps are correctly counted."""
        date_start1 = fields.Datetime.now() + timedelta(days=170)
        date_end1 = date_start1 + timedelta(days=10)
        
        # Second booking overlaps only part of first
        date_start2 = date_start1 + timedelta(days=5)
        date_end2 = date_start2 + timedelta(days=10)
        
        # First booking: 15 units
        booking1 = self._create_booking(
            self.product, 15, date_start1, date_end1, state='reserved'
        )
        
        # Second booking: 10 units (15 + 10 > 20 during overlap) should fail
        with self.assertRaises(ValidationError):
            self._create_booking(
                self.product, 10, date_start2, date_end2, state='planned'
            )
        
        # But 5 units should work (15 + 5 = 20)
        booking3 = self._create_booking(
            self.product, 5, date_start2, date_end2, state='reserved'
        )
        self.assertEqual(booking3.state, 'reserved')

    def test_20_dashboard_data_returns_structure(self):
        """Test that get_dashboard_data returns proper structure."""
        result = self.env['tl.rental.booking'].get_dashboard_data()
        
        self.assertIn('total_bookings', result)
        self.assertIn('active_rentals', result)
        self.assertIn('starting_today', result)
        self.assertIn('ending_today', result)
        self.assertIn('overdue', result)
        self.assertIn('state_counts', result)
        self.assertIn('recent_bookings', result)
        
        # Check state_counts has all states
        for state in ['draft', 'planned', 'reserved', 'ongoing', 'finished', 'returned', 'cancelled']:
            self.assertIn(state, result['state_counts'])

    def test_21_availability_grid_with_multiple_products(self):
        """Test availability grid with multiple products."""
        # Create second product with stock.quant for fleet capacity
        product2 = self.env['product.product'].create({
            'name': 'Test Rental Product 2',
            'type': 'consu',
            'default_code': 'TEST-RENTAL-2',
        })
        self.env['stock.quant'].create({
            'product_id': product2.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'quantity': 10.0,
        })
        
        result = self.env['tl.rental.booking.line'].get_availability_grid(
            product_ids=[self.product.id, product2.id],
            date_start=fields.Datetime.now(),
            week_count=4,
            warehouse_id=self.warehouse.id,
            company_id=self.company.id,
        )
        
        self.assertEqual(len(result['rows']), 2)
        # First product has capacity 20
        self.assertEqual(result['rows'][0]['fleet_capacity'], 20.0)
        # Second product has capacity 10
        self.assertEqual(result['rows'][1]['fleet_capacity'], 10.0)

    def test_22_booking_creates_pickings(self):
        """Test that action_reserve creates outbound and return pickings."""
        date_start = fields.Datetime.now() + timedelta(days=180)
        date_end = date_start + timedelta(days=5)
        
        booking = self._create_booking(
            self.product, 5, date_start, date_end, state='reserved'
        )
        
        # Check pickings were created
        pickings = self.env['stock.picking'].search([
            ('tlrm_booking_id', '=', booking.id)
        ])
        
        # Should have outbound (out) and return (in) picking
        self.assertEqual(len(pickings), 2)
        directions = pickings.mapped('tlrm_direction')
        self.assertIn('out', directions)
        self.assertIn('in', directions)
