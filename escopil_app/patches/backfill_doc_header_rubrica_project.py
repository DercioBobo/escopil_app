from __future__ import unicode_literals

import frappe

# Older Purchase Orders / Purchase Invoices / Sales Invoices carried the project
# and rubrica only on the line items. The Project Dashboard now reads both from
# the document header. Where the header is blank and every line that has a value
# agrees on a single one, copy it up to the header. Documents whose lines hold
# more than one distinct value are left untouched and logged, for a human to
# resolve (they break the "one document == one rubrica, one project" rule).

# parent doctype -> (child doctype, header fields to backfill from the lines)
SPECS = {
	"Purchase Order": ("Purchase Order Item", ("project", "custom_rubrica")),
	"Purchase Invoice": ("Purchase Invoice Item", ("project", "custom_rubrica")),
	"Sales Invoice": ("Sales Invoice Item", ("project",)),
}


def execute():
	conflicts = []
	filled = 0

	for parent_dt, (child_dt, fields) in SPECS.items():
		names = frappe.get_all(parent_dt, filters={"docstatus": 1}, pluck="name")
		for name in names:
			header = frappe.db.get_value(parent_dt, name, fields, as_dict=True)
			patch = {}

			for field in fields:
				if header.get(field):
					continue
				line_values = sorted({
					v for v in frappe.get_all(
						child_dt, filters={"parent": name}, pluck=field
					) if v
				})
				if len(line_values) == 1:
					patch[field] = line_values[0]
				elif len(line_values) > 1:
					conflicts.append(
						"{0} {1}: {2} = {3}".format(parent_dt, name, field, line_values)
					)

			if patch:
				frappe.db.set_value(parent_dt, name, patch, update_modified=False)
				filled += 1

	frappe.db.commit()

	if conflicts:
		frappe.log_error(
			message="Linhas com projeto/rubrica divergentes — cabeçalho não preenchido:\n"
			+ "\n".join(sorted(conflicts)),
			title="backfill_doc_header_rubrica_project",
		)

	print("backfill_doc_header_rubrica_project: {0} cabeçalhos preenchidos, {1} conflitos".format(
		filled, len(conflicts)
	))
