from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import create_billing_entries_from_sales_invoice


def execute():
	invoice_names = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1},
		pluck="name",
	)
	for name in invoice_names:
		already_synced = frappe.db.exists(
			"Project Billing Entry",
			{"reference_doctype": "Sales Invoice", "reference_name": name},
		)
		if already_synced:
			continue

		doc = frappe.get_doc("Sales Invoice", name)
		if any(item.project for item in doc.items):
			create_billing_entries_from_sales_invoice(doc)
