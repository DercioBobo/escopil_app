from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import create_cost_entries_from_stock_entry


def execute():
	se_names = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": 1, "stock_entry_type": "Material Issue"},
		pluck="name",
	)
	for name in se_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Stock Entry", "reference_name": name},
		)
		if already_synced:
			continue

		doc = frappe.get_doc("Stock Entry", name)
		if doc.project:
			create_cost_entries_from_stock_entry(doc)
