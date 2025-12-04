/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

const actionRegistry = registry.category("actions");

export class TlrmAvailabilityAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            grid: null,
            searchQuery: "",
            sortOrder: "asc", // "asc" or "desc"
            weekOffset: 0, // offset in weeks from current date
        });

        onWillStart(async () => {
            await this.loadGrid();
        });
    }

    async loadGrid() {
        this.state.loading = true;
        this.state.error = null;
        try {
            // Include all products for now, limit to 100
            const productDomain = [];
            console.log("TLRM: Starting to load products...");
            const products = await this.orm.searchRead(
                "product.product",
                productDomain,
                ["id"],
                { limit: 100 }
            );
            console.log("TLRM: Found products:", products.length);
            const productIds = products.map((p) => p.id);

            if (productIds.length === 0) {
                console.log("TLRM: No products found, showing empty grid");
                this.state.grid = { columns: [], rows: [] };
                this.state.loading = false;
                return;
            }

            console.log("TLRM: Calling get_availability_grid with", productIds.length, "products");
            // Calculate start date based on week offset (Odoo format: YYYY-MM-DD HH:MM:SS)
            const startDate = new Date();
            startDate.setDate(startDate.getDate() + (this.state.weekOffset * 7));
            const pad = (n) => String(n).padStart(2, '0');
            const dateStr = `${startDate.getFullYear()}-${pad(startDate.getMonth() + 1)}-${pad(startDate.getDate())} ${pad(startDate.getHours())}:${pad(startDate.getMinutes())}:${pad(startDate.getSeconds())}`;

            const grid = await this.orm.call(
                "tl.rental.booking.line",
                "get_availability_grid",
                [productIds],
                {
                    date_start: dateStr,
                    week_count: 12,
                    warehouse_id: null,
                    needed_by_product: {},
                }
            );
            console.log("TLRM: Grid loaded successfully", grid);

            this.state.grid = grid;
        } catch (error) {
            console.error("Failed to load rental availability grid", error);
            this.state.error = error && error.message ? error.message : String(error);
        } finally {
            this.state.loading = false;
        }
    }

    openProduct(productId) {
        if (!productId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openBookingsForCell(productId, columnKey, startDate, endDate) {
        if (!productId || !startDate || !endDate) {
            return;
        }
        // Find the product name for the title
        const row = this.rows.find(r => r.product_id === productId);
        const productName = row ? row.display_name : 'Product';
        
        // Open bookings (not lines) that have this product in their lines
        // and overlap with the selected period
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `Bookings: ${productName} (${columnKey})`,
            res_model: "tl.rental.booking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [
                ["line_ids.product_id", "=", productId],
                ["state", "in", ["reserved", "ongoing"]],
                ["date_start", "<", endDate],
                ["date_end", ">", startDate],
            ],
            context: {
                create: false,
            },
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    toggleSort() {
        this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
    }

    async previousWeeks() {
        this.state.weekOffset -= 12;
        await this.reloadGrid();
    }

    async nextWeeks() {
        this.state.weekOffset += 12;
        await this.reloadGrid();
    }

    async goToToday() {
        this.state.weekOffset = 0;
        await this.reloadGrid();
    }

    async reloadGrid() {
        // Reload grid without showing full loading state
        try {
            const productIds = (this.state.grid?.rows || []).map(r => r.product_id);
            if (productIds.length === 0) {
                return;
            }
            
            const startDate = new Date();
            startDate.setDate(startDate.getDate() + (this.state.weekOffset * 7));
            const pad = (n) => String(n).padStart(2, '0');
            const dateStr = `${startDate.getFullYear()}-${pad(startDate.getMonth() + 1)}-${pad(startDate.getDate())} ${pad(startDate.getHours())}:${pad(startDate.getMinutes())}:${pad(startDate.getSeconds())}`;

            const grid = await this.orm.call(
                "tl.rental.booking.line",
                "get_availability_grid",
                [productIds],
                {
                    date_start: dateStr,
                    week_count: 12,
                    warehouse_id: null,
                    needed_by_product: {},
                }
            );
            this.state.grid = grid;
        } catch (error) {
            console.error("Failed to reload grid", error);
        }
    }

    get columns() {
        return (this.state.grid && this.state.grid.columns) || [];
    }

    get rows() {
        let rows = (this.state.grid && this.state.grid.rows) || [];
        
        // Filter by search query
        const query = (this.state.searchQuery || "").toLowerCase().trim();
        if (query) {
            rows = rows.filter((row) => {
                const name = (row.display_name || "").toLowerCase();
                const code = (row.default_code || "").toLowerCase();
                return name.includes(query) || code.includes(query);
            });
        }
        
        // Sort by product name
        rows = [...rows].sort((a, b) => {
            const nameA = (a.display_name || "").toLowerCase();
            const nameB = (b.display_name || "").toLowerCase();
            if (this.state.sortOrder === "asc") {
                return nameA.localeCompare(nameB);
            } else {
                return nameB.localeCompare(nameA);
            }
        });
        
        return rows;
    }

    get sortIcon() {
        return this.state.sortOrder === "asc" ? "↑" : "↓";
    }

    /**
     * Calculate cell background color based on booking ratio.
     * Green (0%) → Yellow (75%) → Red (100%)
     * Uses smooth gradient interpolation.
     */
    getCellColor(cell, baseCapacity) {
        const capacity = baseCapacity || 0;
        const booked = cell.booked || 0;

        // If no capacity, show red (full)
        if (capacity <= 0) {
            return "#f5c6cb";
        }

        // Calculate ratio: 0 = nothing booked (green), 1 = fully booked (red)
        const ratio = Math.min(booked / capacity, 1);

        // Color stops: green (#c3e6cb) → yellow (#ffeeba) → red (#f5c6cb)
        // Green RGB: 195, 230, 203
        // Yellow RGB: 255, 238, 186
        // Red RGB: 245, 198, 203

        let r, g, b;
        if (ratio <= 0.75) {
            // Green to Yellow (0% to 75%)
            const t = ratio / 0.75; // normalize to 0-1
            r = Math.round(195 + (255 - 195) * t);
            g = Math.round(230 + (238 - 230) * t);
            b = Math.round(203 + (186 - 203) * t);
        } else {
            // Yellow to Red (75% to 100%)
            const t = (ratio - 0.75) / 0.25; // normalize to 0-1
            r = Math.round(255 + (245 - 255) * t);
            g = Math.round(238 + (198 - 238) * t);
            b = Math.round(186 + (203 - 186) * t);
        }

        return `rgb(${r}, ${g}, ${b})`;
    }
}

TlrmAvailabilityAction.template = "tl_rental_manager.TlrmAvailabilityAction";
TlrmAvailabilityAction.props = { "*": true };

actionRegistry.add("tlrm_availability_global", TlrmAvailabilityAction);
