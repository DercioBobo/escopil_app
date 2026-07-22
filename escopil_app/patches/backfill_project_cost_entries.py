from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import create_cost_entries_from_purchase_invoice


def execute():
	invoice_names = frappe.get_all(
		"Purchase Invoice",
		filters={"docstatus": 1},
		pluck="name",
	)
	for name in invoice_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Purchase Invoice", "reference_name": name},
		)
		if already_synced:
			continue

		doc = frappe.get_doc("Purchase Invoice", name)
		if any(item.project and item.get("custom_rubrica") for item in doc.items):
			create_cost_entries_from_purchase_invoice(doc)
