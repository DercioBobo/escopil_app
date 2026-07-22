from __future__ import unicode_literals

import frappe
from frappe.utils import flt


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
			}).insert(ignore_permissions=True), flag="in_project_cost_sync")


def remove_cost_entries_from_purchase_invoice(doc, method=None):
	names = frappe.get_all(
		"Project Cost Entry",
		filters={"reference_doctype": "Purchase Invoice", "reference_name": doc.name},
		pluck="name",
	)
	for name in names:
		_sync(lambda: frappe.delete_doc("Project Cost Entry", name, ignore_permissions=True), flag="in_project_cost_sync")


def create_billing_entries_from_sales_invoice(doc, method=None):
	amount_by_project = {}
	for item in doc.items:
		if item.project:
			amount_by_project[item.project] = amount_by_project.get(item.project, 0) + flt(item.base_net_amount)

	for project, amount in amount_by_project.items():
		_sync(lambda project=project, amount=amount: frappe.get_doc({
			"doctype": "Project Billing Entry",
			"project": project,
			"month": doc.posting_date,
			"billable_amount": amount,
			"source_type": "Sales Invoice",
			"reference_doctype": "Sales Invoice",
			"reference_name": doc.name,
			"is_auto_generated": 1,
		}).insert(ignore_permissions=True), flag="in_project_billing_sync")


def remove_billing_entries_from_sales_invoice(doc, method=None):
	names = frappe.get_all(
		"Project Billing Entry",
		filters={"reference_doctype": "Sales Invoice", "reference_name": doc.name},
		pluck="name",
	)
	for name in names:
		_sync(lambda name=name: frappe.delete_doc("Project Billing Entry", name, ignore_permissions=True), flag="in_project_billing_sync")


def _sync(action, flag="in_project_cost_sync"):
	frappe.flags[flag] = True
	try:
		action()
	finally:
		frappe.flags[flag] = False
