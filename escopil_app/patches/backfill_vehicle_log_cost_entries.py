from __future__ import unicode_literals

import frappe

from escopil_app.project_management.utils import create_cost_entries_from_vehicle_log


def execute():
	vl_names = frappe.get_all(
		"Vehicle Log",
		filters={"docstatus": 1},
		pluck="name",
	)
	for name in vl_names:
		already_synced = frappe.db.exists(
			"Project Cost Entry",
			{"reference_doctype": "Vehicle Log", "reference_name": name},
		)
		if already_synced:
			continue

		doc = frappe.get_doc("Vehicle Log", name)
		if doc.get("project"):
			create_cost_entries_from_vehicle_log(doc)
