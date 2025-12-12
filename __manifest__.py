{
    'name': 'TL Inventor BOM Import',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Import Bill of Materials from Autodesk Inventor',
    'description': """
        Import BOM data from Autodesk Inventor export files.
        
        Features:
        - Import products from Inventor BOM Excel exports
        - Import BOM to booking lines in TL Rental Manager
        - Automatic weight parsing (kg)
        - Duplicate detection and aggregation
        
        Requirements:
        - openpyxl library (pip install openpyxl)
    """,
    'author': 'simonlundmark1',
    'website': 'https://github.com/simonlundmark1',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'stock',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
