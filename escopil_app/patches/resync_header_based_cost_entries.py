from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import (
	_sync,
	_sync_missing_billing_entries,
	_sync_missing_cost_entries,
	_sync_missing_petty_cash_entries,
	_sync_missing_stock_entry_cost_entries,
	_sync_missing_vehicle_log_cost_entries,
	create_billing_entries_from_sales_invoice,
	create_cost_entries_from_purchase_invoice,
	create_cost_entries_from_purchase_order,
)

# Project Cost / Billing Entries from these sources used to be created per line
# item (base_net_amount, line rubrica / line project). They are now created once
# per document from the header total (base_grand_total, c/ IVA) and the header
# rubrica / project.
#
# This patch rebuilds the auto-generated entries on the new basis, but ONLY for
# source documents whose header actually carries the fields we now read. If the
# header is blank (older docs that only had the data on the line items), the old
# line-based entries are left untouched and the doc is logged, so nothing is lost
# silently. backfill_doc_header_rubrica_project runs first and fills most of
# those headers from the lines; whatever it could not resolve (mixed lines) shows
# up in this patch's Error Log for a human to fix, then a project sync picks it up.
#
# After rebuilding, it also runs the "sync missing" pass for every cost-control
# project, so docs the old line-based logic never created an entry for are caught.


def _pi_ready(doc):
	return bool(doc.get("project") and doc.get("custom_rubrica"))


def _po_ready(doc):
	return bool(doc.get("project") and doc.get("custom_rubrica"))


def _si_ready(doc):
	return bool(doc.get("project"))


# entry_doctype -> (sync_flag, {source_doctype: (recreate_fn, header_ready_fn)})
PLAN = {
	"Project Cost Entry": (
		"in_project_cost_sync",
		{
			"Purchase Invoice": (create_cost_entries_from_purchase_invoice, _pi_ready),
			"Purchase Order": (create_cost_entries_from_purchase_order, _po_ready),
		},
	),
	"Project Billing Entry": (
		"in_project_billing_sync",
		{
			"Sales Invoice": (create_billing_entries_from_sales_invoice, _si_ready),
		},
	),
}


def execute():
	skipped = []

	for entry_doctype, (sync_flag, recreators) in PLAN.items():
		entries = frappe.get_all(
			entry_doctype,
			filters={
				"is_auto_generated": 1,
				"reference_doctype": ["in", list(recreators)],
			},
			fields=["name", "reference_doctype", "reference_name"],
		)

		names_by_source = {}
		for entry in entries:
			names_by_source.setdefault(entry.reference_doctype, set()).add(entry.reference_name)

		for source_doctype, names in names_by_source.items():
			recreate, is_ready = recreators[source_doctype]
			for name in names:
				if not frappe.db.exists(source_doctype, name):
					continue
				doc = frappe.get_doc(source_doctype, name)
				if doc.docstatus != 1 or not is_ready(doc):
					# header not populated — keep the old line-based entries as-is
					skipped.append("{0} {1}".format(source_doctype, name))
					continue

				old = frappe.get_all(
					entry_doctype,
					filters={
						"is_auto_generated": 1,
						"reference_doctype": source_doctype,
						"reference_name": name,
					},
					pluck="name",
				)
				for old_name in old:
					_sync(
						lambda dt=entry_doctype, n=old_name: frappe.delete_doc(
							dt, n, ignore_permissions=True, force=True
						),
						flag=sync_flag,
					)
				recreate(doc)

	if skipped:
		frappe.log_error(
			message="Cabeçalho sem rubrica/projeto — lançamentos antigos mantidos, não migrados:\n"
			+ "\n".join(sorted(skipped)),
			title="resync_header_based_cost_entries",
		)

	# headers are populated by now (see backfill_doc_header_rubrica_project), so
	# create any entry the old line-based logic never made for a doc it skipped
	projects = frappe.get_all(
		"Project", filters={"custom_cost_control_enabled": 1}, pluck="name"
	)
	for project in projects:
		_sync_missing_cost_entries(project)
		_sync_missing_petty_cash_entries(project)
		_sync_missing_stock_entry_cost_entries(project)
		_sync_missing_vehicle_log_cost_entries(project)
		_sync_missing_billing_entries(project)
