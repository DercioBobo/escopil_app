from __future__ import unicode_literals

import frappe


def create_cost_entries_from_purchase_invoice(doc, method=None):
	for item in doc.items:
		if item.project and item.get("custom_rubrica"):
			_sync(lambda: frappe.get_doc({
				"doctype": "Project Cost Entry",
				"project": item.project,
				"rubrica": item.custom_rubrica,
				"posting_date": doc.posting_date,
				"amount": item.base_net_amount,
				"source_type": "Purchase Invoice",
				"reference_doctype": "Purchase Invoice",
				"reference_name": doc.name,
				"is_auto_generated": 1,
			}).insert(ignore_permissions=True))


def remove_cost_entries_from_purchase_invoice(doc, method=None):
	names = frappe.get_all(
		"Project Cost Entry",
		filters={"reference_doctype": "Purchase Invoice", "reference_name": doc.name},
		pluck="name",
	)
	for name in names:
		_sync(lambda: frappe.delete_doc("Project Cost Entry", name, ignore_permissions=True))


def _sync(action):
	frappe.flags.in_project_cost_sync = True
	try:
		action()
	finally:
		frappe.flags.in_project_cost_sync = False
