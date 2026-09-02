from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import (
	_sync,
	create_cost_entries_from_purchase_invoice,
	create_cost_entries_from_purchase_order,
)

# Project Cost Entries from these sources used to be created per line item
# (base_net_amount, line rubrica). They are now created once per document from
# the header total (base_grand_total, c/ IVA) and the header rubrica. Wipe the
# auto-generated ones and rebuild them on the new basis.
RECREATORS = {
	"Purchase Invoice": create_cost_entries_from_purchase_invoice,
	"Purchase Order": create_cost_entries_from_purchase_order,
}


def execute():
	entries = frappe.get_all(
		"Project Cost Entry",
		filters={
			"is_auto_generated": 1,
			"reference_doctype": ["in", list(RECREATORS)],
		},
		fields=["name", "reference_doctype", "reference_name"],
	)

	refs_by_doctype = {}
	for entry in entries:
		refs_by_doctype.setdefault(entry.reference_doctype, set()).add(entry.reference_name)
		_sync(
			lambda name=entry.name: frappe.delete_doc(
				"Project Cost Entry", name, ignore_permissions=True, force=True
			),
			flag="in_project_cost_sync",
		)

	skipped = []
	for doctype, names in refs_by_doctype.items():
		recreate = RECREATORS[doctype]
		for name in names:
			if not frappe.db.exists(doctype, name):
				continue
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus != 1:
				continue
			if not (doc.get("project") and doc.get("custom_rubrica")):
				skipped.append("{0} {1}".format(doctype, name))
				continue
			recreate(doc)

	if skipped:
		frappe.log_error(
			message="Sem rubrica/projeto no cabeçalho, lançamento de custo não recriado:\n"
			+ "\n".join(skipped),
			title="resync_header_based_cost_entries",
		)
