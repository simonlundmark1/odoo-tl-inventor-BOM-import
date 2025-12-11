/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { jsonrpc } from "@web/core/network/rpc";

/**
 * Booking Availability Wizard
 * 
 * A modal dialog that shows availability for all products in a booking,
 * allows selecting a date range by clicking/dragging, and validates
 * that all products are available for the selected period.
 */
export class BookingAvailabilityWizard extends Component {
    static template = "tl_rental_manager.BookingAvailabilityWizard";
    static components = { Dialog };
    static props = {
        bookingId: { type: Number, optional: true },
        bookingLines: { type: Array },  // [{product_id, product_name, quantity}]
        warehouseId: { type: Number, optional: true },
        companyId: { type: Number, optional: true },
        onConfirm: { type: Function },  // Called with {dateStart, dateEnd}
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            error: null,
            viewMode: "week",  // "week" or "day"
            weekOffset: 0,
            grid: null,
            // Selection state
            selectionStart: null,  // {rowIndex, colIndex} or null
            selectionEnd: null,
            isSelecting: false,
            // Warehouse state
            warehouses: [],
            selectedWarehouseId: this.props.warehouseId || null,
        });

        onWillStart(async () => {
            await this.loadWarehouses();
            await this.loadGrid();
        });
    }

    async loadWarehouses() {
        try {
            const result = await jsonrpc('/tlrm/warehouses', {
                company_id: this.props.companyId || null,
            });
            this.state.warehouses = result.warehouses || [];
        } catch (error) {
            console.error("Failed to load warehouses", error);
            this.state.warehouses = [];
        }
    }

    async onWarehouseChange(ev) {
        const value = ev.target.value;
        this.state.selectedWarehouseId = value ? parseInt(value, 10) : null;
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
        await this.loadGrid();
    }

    get selectedWarehouseName() {
        if (!this.state.selectedWarehouseId) {
            return "All Warehouses";
        }
        const wh = this.state.warehouses.find(w => w.id === this.state.selectedWarehouseId);
        return wh ? wh.name : "Unknown";
    }

    async loadGrid() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const productIds = this.props.bookingLines.map(l => l.product_id);
            const neededByProduct = {};
            for (const line of this.props.bookingLines) {
                neededByProduct[line.product_id] = (neededByProduct[line.product_id] || 0) + line.quantity;
            }

            if (productIds.length === 0) {
                this.state.grid = { columns: [], rows: [] };
                this.state.loading = false;
                return;
            }

            const startDate = new Date();
            startDate.setDate(startDate.getDate() + (this.state.weekOffset * 7));
            const pad = (n) => String(n).padStart(2, '0');
            const dateStr = `${startDate.getFullYear()}-${pad(startDate.getMonth() + 1)}-${pad(startDate.getDate())} 00:00:00`;

            const periodCount = this.state.viewMode === "week" ? 12 : 28;  // 12 weeks or 28 days

            const grid = await this.orm.call(
                "tl.rental.booking.line",
                "get_availability_grid",
                [productIds],
                {
                    date_start: dateStr,
                    week_count: this.state.viewMode === "week" ? periodCount : Math.ceil(periodCount / 7),
                    warehouse_id: this.state.selectedWarehouseId,
                    company_id: this.props.companyId || null,
                    needed_by_product: neededByProduct,
                }
            );

            // If day view, we need to expand weeks into days
            if (this.state.viewMode === "day") {
                this.state.grid = this.expandToDays(grid);
            } else {
                this.state.grid = grid;
            }
        } catch (error) {
            console.error("Failed to load booking availability grid", error);
            this.state.error = error?.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    expandToDays(weekGrid) {
        // Convert week-based grid to day-based grid
        const dayColumns = [];
        const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        
        for (const week of weekGrid.columns) {
            const startDt = new Date(week.start);
            for (let d = 0; d < 7; d++) {
                const dayDt = new Date(startDt);
                dayDt.setDate(dayDt.getDate() + d);
                const endDt = new Date(dayDt);
                endDt.setDate(endDt.getDate() + 1);
                
                dayColumns.push({
                    key: dayDt.toISOString().split('T')[0],
                    label: `${dayNames[d]} ${dayDt.getDate()}/${dayDt.getMonth() + 1}`,
                    start: dayDt.toISOString(),
                    end: endDt.toISOString(),
                });
            }
        }

        // For simplicity, we'll use the same availability for all days in a week
        // A more accurate implementation would query day-by-day
        const dayRows = weekGrid.rows.map(row => {
            const dayCells = [];
            for (let i = 0; i < row.cells.length; i++) {
                const weekCell = row.cells[i];
                for (let d = 0; d < 7; d++) {
                    dayCells.push({
                        ...weekCell,
                        column_key: dayColumns[i * 7 + d]?.key,
                    });
                }
            }
            return { ...row, cells: dayCells };
        });

        return {
            ...weekGrid,
            columns: dayColumns.slice(0, 28),  // Limit to 28 days (4 weeks)
            rows: dayRows.map(r => ({ ...r, cells: r.cells.slice(0, 28) })),
        };
    }

    get columns() {
        return this.state.grid?.columns || [];
    }

    get rows() {
        return this.state.grid?.rows || [];
    }

    get neededByProduct() {
        const needed = {};
        for (const line of this.props.bookingLines) {
            needed[line.product_id] = (needed[line.product_id] || 0) + line.quantity;
        }
        return needed;
    }

    // Selection handling
    onCellMouseDown(rowIndex, colIndex) {
        this.state.selectionStart = { rowIndex: null, colIndex };  // Select all rows for this column
        this.state.selectionEnd = { rowIndex: null, colIndex };
        this.state.isSelecting = true;
    }

    onCellMouseEnter(rowIndex, colIndex) {
        if (this.state.isSelecting && this.state.selectionStart) {
            this.state.selectionEnd = { rowIndex: null, colIndex };
        }
    }

    onCellMouseUp() {
        this.state.isSelecting = false;
    }

    onColumnClick(colIndex) {
        // Single click on column header selects just that column
        this.state.selectionStart = { rowIndex: null, colIndex };
        this.state.selectionEnd = { rowIndex: null, colIndex };
        this.state.isSelecting = false;
    }

    isColumnSelected(colIndex) {
        if (!this.state.selectionStart || !this.state.selectionEnd) {
            return false;
        }
        const startCol = Math.min(this.state.selectionStart.colIndex, this.state.selectionEnd.colIndex);
        const endCol = Math.max(this.state.selectionStart.colIndex, this.state.selectionEnd.colIndex);
        return colIndex >= startCol && colIndex <= endCol;
    }

    isCellSelected(rowIndex, colIndex) {
        return this.isColumnSelected(colIndex);
    }

    getCellColor(cell, baseCapacity, isSelected) {
        const capacity = baseCapacity || 0;
        const booked = cell.booked || 0;
        const needed = this.neededByProduct[cell.product_id] || cell.needed || 0;
        const available = cell.available || 0;

        // If selected, check if this product fits
        if (isSelected && needed > 0) {
            if (available >= needed) {
                return "#c3e6cb";  // Green - fits
            } else {
                return "#f5c6cb";  // Red - doesn't fit
            }
        }

        // Default gradient coloring
        if (capacity <= 0) {
            return "#f5c6cb";
        }

        const ratio = Math.min(booked / capacity, 1);
        let r, g, b;
        if (ratio <= 0.75) {
            const t = ratio / 0.75;
            r = Math.round(195 + (255 - 195) * t);
            g = Math.round(230 + (238 - 230) * t);
            b = Math.round(203 + (186 - 203) * t);
        } else {
            const t = (ratio - 0.75) / 0.25;
            r = Math.round(255 + (245 - 255) * t);
            g = Math.round(238 + (198 - 238) * t);
            b = Math.round(186 + (203 - 186) * t);
        }
        return `rgb(${r}, ${g}, ${b})`;
    }

    // Summary for selected range
    get selectionSummary() {
        if (!this.state.selectionStart || !this.state.selectionEnd) {
            return null;
        }

        const startCol = Math.min(this.state.selectionStart.colIndex, this.state.selectionEnd.colIndex);
        const endCol = Math.max(this.state.selectionStart.colIndex, this.state.selectionEnd.colIndex);
        
        const columns = this.columns;
        const rows = this.rows;
        const needed = this.neededByProduct;

        let allFit = true;
        let fitCount = 0;
        const productStatus = [];

        for (const row of rows) {
            const productNeeded = needed[row.product_id] || 0;
            let productFits = true;

            for (let c = startCol; c <= endCol; c++) {
                const cell = row.cells[c];
                if (cell && productNeeded > 0 && cell.available < productNeeded) {
                    productFits = false;
                    break;
                }
            }

            productStatus.push({
                product_id: row.product_id,
                display_name: row.display_name,
                needed: productNeeded,
                fits: productFits,
            });

            if (productFits) {
                fitCount++;
            } else {
                allFit = false;
            }
        }

        const startDate = columns[startCol]?.start;
        const endDate = columns[endCol]?.end;

        return {
            startCol,
            endCol,
            startDate,
            endDate,
            startLabel: columns[startCol]?.label,
            endLabel: columns[endCol]?.label,
            allFit,
            fitCount,
            totalCount: rows.length,
            productStatus,
        };
    }

    get canConfirm() {
        const summary = this.selectionSummary;
        return summary && summary.allFit && summary.startDate && summary.endDate;
    }

    // Navigation
    async previousPeriod() {
        this.state.weekOffset -= (this.state.viewMode === "week" ? 12 : 4);
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
        await this.loadGrid();
    }

    async nextPeriod() {
        this.state.weekOffset += (this.state.viewMode === "week" ? 12 : 4);
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
        await this.loadGrid();
    }

    async goToToday() {
        this.state.weekOffset = 0;
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
        await this.loadGrid();
    }

    async toggleViewMode() {
        this.state.viewMode = this.state.viewMode === "week" ? "day" : "week";
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
        await this.loadGrid();
    }

    clearSelection() {
        this.state.selectionStart = null;
        this.state.selectionEnd = null;
    }

    onConfirm() {
        const summary = this.selectionSummary;
        if (summary && summary.allFit) {
            this.props.onConfirm({
                dateStart: summary.startDate,
                dateEnd: summary.endDate,
            });
            this.props.close();
        }
    }

    onCancel() {
        this.props.close();
    }
}

// Register as a service that can be called from form views
export const bookingAvailabilityWizardService = {
    dependencies: ["dialog"],
    start(env, { dialog }) {
        return {
            open(params) {
                return dialog.add(BookingAvailabilityWizard, params);
            },
        };
    },
};

registry.category("services").add("tlrm_booking_availability_wizard", bookingAvailabilityWizardService);
