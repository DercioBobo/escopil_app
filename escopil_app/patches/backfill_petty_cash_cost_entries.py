from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import create_cost_entries_from_purchase_order


def execute():
	po_names = frappe.get_all(
		"Purchase Order",
		filters={"docstatus": 1, "buying_mode": "Petty Cash"},
		pluck="name",
	)
	for name in po_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Purchase Order", "reference_name": name},
		)
		if already_synced:
			continue

		doc = frappe.get_doc("Purchase Order", name)
		if any(item.project and item.get("custom_rubrica") for item in doc.items):
			create_cost_entries_from_purchase_order(doc)
