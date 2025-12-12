-- =============================================================================
-- TL Rental Manager - Database Reset Script
-- =============================================================================
-- This script deletes all rental bookings, stock moves, and products.
-- It preserves: warehouses, locations, users, companies, projects, etc.
--
-- Usage:
--   psql -U admin -d db -f reset_rental_data.sql
--   OR copy-paste into psql/pgAdmin
--
-- WARNING: This is destructive! Make a backup first if needed.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. RENTAL BOOKINGS (tl_rental_manager module data)
-- -----------------------------------------------------------------------------

-- Delete stock moves linked to rental pickings
DELETE FROM stock_move_line 
WHERE move_id IN (
    SELECT id FROM stock_move 
    WHERE picking_id IN (SELECT id FROM stock_picking WHERE tlrm_booking_id IS NOT NULL)
);

DELETE FROM stock_move 
WHERE picking_id IN (SELECT id FROM stock_picking WHERE tlrm_booking_id IS NOT NULL);

-- Delete rental pickings
DELETE FROM stock_picking WHERE tlrm_booking_id IS NOT NULL;

-- Delete booking lines and bookings
DELETE FROM tl_rental_booking_line;
DELETE FROM tl_rental_booking;

-- Reset booking sequence
UPDATE ir_sequence SET number_next = 1 WHERE code = 'tl.rental.booking';

-- -----------------------------------------------------------------------------
-- 2. STOCK DATA (quants, moves, pickings)
-- -----------------------------------------------------------------------------

-- Delete all stock quants (inventory quantities)
DELETE FROM stock_quant;

-- Delete all stock move lines
DELETE FROM stock_move_line;

-- Delete all stock moves
DELETE FROM stock_move;

-- Delete all pickings (optional - comment out if you want to keep non-rental pickings)
DELETE FROM stock_picking;

-- -----------------------------------------------------------------------------
-- 3. PRODUCTS
-- -----------------------------------------------------------------------------

-- Delete product supplier info
DELETE FROM product_supplierinfo;

-- Delete product pricelist items referencing products
DELETE FROM product_pricelist_item WHERE product_id IS NOT NULL OR product_tmpl_id IS NOT NULL;

-- Delete product tags relations
DELETE FROM product_tag_product_product_rel;
DELETE FROM product_tag_product_template_rel;

-- Delete product attribute values
DELETE FROM product_template_attribute_value;
DELETE FROM product_template_attribute_line;

-- Delete product variants
DELETE FROM product_product;

-- Delete product templates
DELETE FROM product_template;

-- -----------------------------------------------------------------------------
-- 4. CLEANUP (optional extras)
-- -----------------------------------------------------------------------------

-- Clean up mail messages related to deleted records (optional)
-- DELETE FROM mail_message WHERE model IN ('tl.rental.booking', 'tl.rental.booking.line', 'product.product', 'product.template');

-- Clean up activities related to deleted records (optional)
-- DELETE FROM mail_activity WHERE res_model IN ('tl.rental.booking', 'tl.rental.booking.line', 'product.product', 'product.template');

COMMIT;

-- -----------------------------------------------------------------------------
-- VERIFICATION
-- -----------------------------------------------------------------------------
SELECT 'Rental bookings:' as table_name, COUNT(*) as count FROM tl_rental_booking
UNION ALL
SELECT 'Booking lines:', COUNT(*) FROM tl_rental_booking_line
UNION ALL
SELECT 'Products:', COUNT(*) FROM product_product
UNION ALL
SELECT 'Product templates:', COUNT(*) FROM product_template
UNION ALL
SELECT 'Stock moves:', COUNT(*) FROM stock_move
UNION ALL
SELECT 'Stock quants:', COUNT(*) FROM stock_quant
UNION ALL
SELECT 'Pickings:', COUNT(*) FROM stock_picking;
