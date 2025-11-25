{
    "name": "Stock Rental Manager",
    "summary": "Manage stockable product rentals and project bookings with availability and calendar planning",
    "version": "19.0.1.0.0",
    "author": "Me",
    "website": "",
    "category": "Inventory",
    "depends": ["base", "product", "stock", "project"],
    "data": [
        "security/ir.model.access.csv",
        "data/rental_sequence.xml",
        "data/rental_cron.xml",
        "views/product_view.xml",
        "views/rental_booking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_rental_manager/static/src/js/rental_calendar.js",
        ],
    },
    "application": True,
    "installable": True,
    "license": "LGPL-3",
}

