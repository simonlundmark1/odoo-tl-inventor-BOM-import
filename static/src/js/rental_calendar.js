/** @odoo-module **/

import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { patch } from "@web/core/utils/patch";

// Show Swedish-style week numbers (V.xx) in calendar for rental bookings
patch(CalendarRenderer.prototype, {
    getOptions() {
        const options = super.getOptions();
        if (this.props.model && this.props.model.resModel === 'stock.rental.booking') {
            options.weekNumbers = true;
            options.weekLabel = "V.";
            options.firstDay = 1;
        }
        return options;
    }
});
