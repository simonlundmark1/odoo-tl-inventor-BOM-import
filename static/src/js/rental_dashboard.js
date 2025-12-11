/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

const actionRegistry = registry.category("actions");

export class TlrmDashboard extends Component {
    static template = "tl_rental_manager.TlrmDashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            data: null,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "tl.rental.booking",
                "get_dashboard_data",
                []
            );
            this.state.data = data;
        } catch (error) {
            console.error("Failed to load dashboard data", error);
            this.state.error = error?.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        await this.loadData();
    }

    openBookings(domain = []) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Bookings",
            res_model: "tl.rental.booking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: domain,
        });
    }

    openBookingsByState(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: this.state.data?.state_counts?.[state]?.label || state,
            res_model: "tl.rental.booking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [["state", "=", state]],
        });
    }

    openOverdue() {
        const now = new Date().toISOString();
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Overdue Bookings",
            res_model: "tl.rental.booking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [
                ["state", "in", ["reserved", "ongoing", "finished"]],
                ["date_end", "<", now],
            ],
        });
    }

    openBooking(bookingId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "tl.rental.booking",
            res_id: bookingId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    createBooking() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Booking",
            res_model: "tl.rental.booking",
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAvailability() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "tlrm_availability_global",
            name: "Rental Availability",
        });
    }

    getStateClass(state) {
        const classes = {
            draft: "bg-secondary",
            reserved: "bg-info",
            ongoing: "bg-warning",
            finished: "bg-primary",
            returned: "bg-success",
            cancelled: "bg-danger",
        };
        return classes[state] || "bg-secondary";
    }

    formatDate(dateStr) {
        if (!dateStr) return "-";
        const date = new Date(dateStr);
        return date.toLocaleDateString("sv-SE", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        });
    }
}

actionRegistry.add("tlrm_dashboard", TlrmDashboard);
