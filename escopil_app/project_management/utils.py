from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import flt


def validate_project_cost_control_tables(doc, method=None):
	_check_duplicate_billing_forecast_months(doc)
	_check_duplicate_budget_rubricas(doc)


def _check_duplicate_billing_forecast_months(doc):
	seen = set()
	for row in doc.get("custom_billing_forecast_overrides") or []:
		if not row.month_name or not row.year:
			continue
		key = (row.month_name, row.year)
		if key in seen:
			frappe.throw(
				_("Já existe uma previsão de faturação para {0}/{1} na tabela de Ajustes Mensais.").format(
					row.month_name, row.year
				)
			)
		seen.add(key)


def _check_duplicate_budget_rubricas(doc):
	seen = set()
	for row in doc.get("custom_budget_rubricas") or []:
		if not row.rubrica:
			continue
		if row.rubrica in seen:
			frappe.throw(
				_("A rubrica {0} já está na tabela de Rubricas do Orçamento.").format(row.rubrica)
			)
		seen.add(row.rubrica)


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


def create_cost_entries_from_purchase_order(doc, method=None):
	# Petty Cash POs never turn into a Purchase Invoice, so they're the real
	# cost here and now, not just a commitment
	if doc.get("buying_mode") != "Petty Cash":
		return

	for item in doc.items:
		if item.project and item.get("custom_rubrica"):
			_sync(lambda item=item: frappe.get_doc({
				"doctype": "Project Cost Entry",
				"project": item.project,
				"rubrica": item.custom_rubrica,
				"posting_date": doc.transaction_date,
				"amount": item.base_net_amount,
				"source_type": "Purchase Order (Petty Cash)",
				"reference_doctype": "Purchase Order",
				"reference_name": doc.name,
				"is_auto_generated": 1,
			}).insert(ignore_permissions=True), flag="in_project_cost_sync")


def remove_cost_entries_from_purchase_order(doc, method=None):
	names = frappe.get_all(
		"Project Cost Entry",
		filters={"reference_doctype": "Purchase Order", "reference_name": doc.name},
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


@frappe.whitelist()
def sync_project_entries(project):
	frappe.has_permission("Project", "write", doc=project, throw=True)

	return {
		"cost_created": _sync_missing_cost_entries(project) + _sync_missing_petty_cash_entries(project),
		"billing_created": _sync_missing_billing_entries(project),
	}


def _sync_missing_cost_entries(project):
	pi_names = frappe.db.sql_list(
		"""
		select distinct pi.name
		from `tabPurchase Invoice` pi
		inner join `tabPurchase Invoice Item` item on item.parent = pi.name
		where pi.docstatus = 1
			and item.project = %s
			and item.custom_rubrica is not null and item.custom_rubrica != ''
		""",
		project,
	)

	created = 0
	for name in pi_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Purchase Invoice", "reference_name": name, "project": project},
		)
		if already_synced:
			continue
		create_cost_entries_from_purchase_invoice(frappe.get_doc("Purchase Invoice", name))
		created += 1
	return created


def _sync_missing_petty_cash_entries(project):
	po_names = frappe.db.sql_list(
		"""
		select distinct po.name
		from `tabPurchase Order` po
		inner join `tabPurchase Order Item` item on item.parent = po.name
		where po.docstatus = 1
			and po.buying_mode = 'Petty Cash'
			and item.project = %s
			and item.custom_rubrica is not null and item.custom_rubrica != ''
		""",
		project,
	)

	created = 0
	for name in po_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Purchase Order", "reference_name": name, "project": project},
		)
		if already_synced:
			continue
		create_cost_entries_from_purchase_order(frappe.get_doc("Purchase Order", name))
		created += 1
	return created


def _sync_missing_billing_entries(project):
	si_names = frappe.db.sql_list(
		"""
		select distinct si.name
		from `tabSales Invoice` si
		inner join `tabSales Invoice Item` item on item.parent = si.name
		where si.docstatus = 1
			and item.project = %s
		""",
		project,
	)

	created = 0
	for name in si_names:
		already_synced = frappe.db.exists(
			"Project Billing Entry",
			{"reference_doctype": "Sales Invoice", "reference_name": name, "project": project},
		)
		if already_synced:
			continue
		create_billing_entries_from_sales_invoice(frappe.get_doc("Sales Invoice", name))
		created += 1
	return created
