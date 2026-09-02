from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import (
	_sync,
	create_billing_entries_from_sales_invoice,
	create_cost_entries_from_purchase_invoice,
	create_cost_entries_from_purchase_order,
)

# Project Cost / Billing Entries from these sources used to be created per line
# item (base_net_amount, line rubrica / line project). They are now created once
# per document from the header total (base_grand_total, c/ IVA) and the header
# rubrica / project. Wipe the auto-generated ones and rebuild them on the new
# basis.
#
# entry_doctype -> {source_doctype: recreate_fn}
PLAN = {
	"Project Cost Entry": {
		"Purchase Invoice": create_cost_entries_from_purchase_invoice,
		"Purchase Order": create_cost_entries_from_purchase_order,
	},
	"Project Billing Entry": {
		"Sales Invoice": create_billing_entries_from_sales_invoice,
	},
}

SYNC_FLAG = {
	"Project Cost Entry": "in_project_cost_sync",
	"Project Billing Entry": "in_project_billing_sync",
}


def execute():
	skipped = []

	for entry_doctype, recreators in PLAN.items():
		entries = frappe.get_all(
			entry_doctype,
			filters={
				"is_auto_generated": 1,
				"reference_doctype": ["in", list(recreators)],
			},
			fields=["name", "reference_doctype", "reference_name"],
		)

		refs_by_doctype = {}
		for entry in entries:
			refs_by_doctype.setdefault(entry.reference_doctype, set()).add(entry.reference_name)
			_sync(
				lambda dt=entry_doctype, name=entry.name: frappe.delete_doc(
					dt, name, ignore_permissions=True, force=True
				),
				flag=SYNC_FLAG[entry_doctype],
			)

		for source_doctype, names in refs_by_doctype.items():
			recreate = recreators[source_doctype]
			for name in names:
				if not frappe.db.exists(source_doctype, name):
					continue
				doc = frappe.get_doc(source_doctype, name)
				if doc.docstatus != 1:
					continue
				recreate(doc)
				if not frappe.db.exists(
					entry_doctype,
					{"reference_doctype": source_doctype, "reference_name": name},
				):
					skipped.append("{0} {1}".format(source_doctype, name))

	if skipped:
		frappe.log_error(
			message="Sem rubrica/projeto no cabeçalho, lançamento não recriado:\n"
			+ "\n".join(skipped),
			title="resync_header_based_cost_entries",
		)
