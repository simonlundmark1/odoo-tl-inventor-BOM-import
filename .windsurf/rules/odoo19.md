---
trigger: always_on
---

Odoo 19 Addon Development Rulebook

Target version: Odoo 19 (strict)
Odoo 18 is referenced only to identify legacy patterns that must NOT be used in new code.

1. Module Structure Rules (Odoo 19 Strict)
1.1 Always use the modern addon structure
your_module/
    __init__.py
    __manifest__.py
    models/
        __init__.py
        ...
    views/
        ...
    security/
        ir.model.access.csv
    data/
        ...
    static/
        src/
            js/
            xml/
            scss/

1.2 Manifest must be a Python dict (no JSON)

Keys must be valid for Odoo 19:

name, summary, version, depends, data, assets, license, installable, etc.

No deprecated manifest keys from older versions.

1.3 Asset loading uses ONLY the assets key in the manifest

Correct Odoo 19 style:

"assets": {
    "web.assets_backend": [
        "module_name/static/src/js/my_script.js",
    ],
}

1.4 Asset XML files (views/assets.xml) are optional

Use them only if you define QWeb templates.
Never use them to inject JS/CSS in Odoo 19.
(That’s manifest-only now.)

2. View Development Rules (Odoo 19 Strict)
2.1 The only valid list view root tag is <list>

Tree views are removed.
Odoo 19 rejects any <tree> usage.

Correct Odoo 19 list view:

<list string="My Items">
    <field name="name"/>
    <field name="date"/>
</list>

If you see:
<tree> ... </tree>


→ This is Odoo 17/older code.
→ Will crash Odoo 19 (“Invalid view type: 'tree'”).

2.2 Inherited list views must also use <list>

Example:

<list position="inside">
    <field name="x_note"/>
</list>

2.3 Valid view types in Odoo 19

list

form

kanban

calendar

gantt

pivot

graph

activity

search

qweb

Anything else is invalid.

2.4 XML must wrap content in <odoo>

Example:

<odoo>
  <record id="..." model="ir.ui.view">
      ...
  </record>
</odoo>

3. ORM, Models, and Python Rules (Odoo 19 Strict)
3.1 NEVER use deprecated attributes / legacy API

Forbidden in Odoo 19 (but existed in earlier versions):

odoo.osv

self._cr

self._uid

self._context

Correct Odoo 19 instead:
self.env.cr
self.env.uid
self.env.context

3.2 Model declaration format (mandatory)
from odoo import models, fields, api

class MyModel(models.Model):
    _name = "my.model"
    _description = "My Model"

    name = fields.Char()

3.3 Domain logic

Odoo 19 supports dynamic date domains.
Examples that are valid in 19:

domain=[("date", ">", fields.Date.today())]


Odoo 18 lacked some of the new dynamic syntax.

3.4 Avoid direct SQL unless necessary

Use:

self.env.cr.execute(...)


Never self._cr.execute(...).

4. Cron Jobs / ir.cron Rules (Odoo 19 Strict)

Odoo 19 removes several fields that existed long ago.

Forbidden in Odoo 19:

numbercall

doall

If your addon contains these, installation will crash.

Valid Odoo 19 cron definition:
<odoo>
  <record id="my_cron" model="ir.cron">
    <field name="name">My Cron</field>
    <field name="active" eval="True"/>
    <field name="model_id" ref="model_my_model"/>
    <field name="state">code</field>
    <field name="code">model._run_cron()</field>
    <field name="interval_number">10</field>
    <field name="interval_type">minutes</field>
    <field name="user_id" ref="base.user_root"/>
  </record>
</odoo>

If you need limited-run jobs:

Implement counters in Python.
You cannot rely on numbercall anymore.

5. JavaScript / Webclient Rules (Odoo 19 Strict)
5.1 Odoo 19 uses OWL

The LLM must generate or reason in terms of OWL components.

Examples:

Component classes

useState(), useEffect(), useService()

async event handlers

Correct import paths: "@web/..."

5.2 No legacy QWeb-based JS widgets

Old-style JS widgets (pre-OWL) should never be generated unless explicitly requested.

5.3 Assets loaded in manifest only

(Repeating for emphasis.)

6. Security / Access Rules (Odoo 19 Strict)
6.1 ir.model.access.csv format stays the same
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink

6.2 Record rules still work normally

Use:

<record id="rule_example" model="ir.rule">
    <field name="name">Example Rule</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[("user_id","=",uid)]</field>
</record>

6.3 Odoo 19 improves access UI

No impact on module code but helpful to remember while debugging.

7. Major Odoo 19-Specific Functional Changes (Developer Impact Only)
7.1 Pivot tables support GROUPING SETS (19 only)

If generating or debugging analytical views in 19, this is allowed.

7.2 Activities app is improved in 19

Activity-related automation or custom views may behave differently compared to 18.

7.3 Website/eCommerce uses more OWL

Templates and JS behavior changed.
LLM must generate OWL-style website customizations.

7.4 Inventory: Odoo 19 supports multi-level packages

If coding stock logic, multi-level packages may appear or must be supported.

8. Debugging Rules (Extremely Important)
8.1 If a view crashes with “Invalid view type”

Your view uses <tree> or wrong tags → Replace with <list>.

8.2 If cron creation fails with "Invalid field ‘numbercall’"

You used obsolete fields → Remove them.

8.3 If Odoo complains “Unknown comodel_name”

→ Missing dependency in depends.
Example:
If code references "sale.order" you MUST add "sale" or "sale_management".

8.4 If a module does not appear in the Apps list:

Checklist:

Folder structure correct

Manifest valid Python

Addons path correct

Restart Odoo service

Remove Apps filter

Look at logs for parse errors

8.5 If JS changes do not load

You forgot the manifest assets section

Or browser cache → hard refresh

Or JS syntax error in OWL component

8.6 If XML fails to load with a line/column error

Most common mistakes:

Missing <odoo> wrapper

Forgotten closing tag

Wrong view tag (<tree> instead of <list>)

9. Migration Rule (18 → 19) for Addons

The LLM must base all reasoning on these core differences:

Required changes:

Replace all <tree> → <list>

Remove cron fields numbercall, doall

Replace deprecated _cr, _uid, _context

Convert QWeb JS widgets → OWL components

Update assets to use manifest-based loading

Check for new constraints in pivot, activities, website

Optional:

Add 19-specific features (AI, grouping sets, multi-level packaging)

10. Direct If/Then Rules for the LLM (Version Enforcement)
10.1 Version enforcement

IF user does not specify a version
→ Use Odoo 19 only.

10.2 View rendering

IF generating any list view
→ Must use <list>.

10.3 Scheduled actions

IF generating cron XML
→ Must not generate numbercall or doall.

10.4 ORM access

IF accessing cursor/user/context
→ Must use self.env.* not deprecated variants.

10.5 JS components

IF generating frontend/backend JS
→ Must use OWL syntax.

10.6 Debug explanations

IF an error resembles patterns from older Odoo (like “Unknown view type 'tree'”)
→ Identify it as a legacy-pattern error and correct to Odoo 19 standard.