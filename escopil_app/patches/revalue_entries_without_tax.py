from __future__ import unicode_literals

import frappe

# Project Billing Entries from Sales Invoices used to carry the invoice total
# c/ IVA (base_grand_total). They now carry the total s/ IVA (base_net_total).
# This re-values the existing auto-generated entries in place from their source
# invoice header. Costs (Purchase Invoice / Purchase Order) stay c/ IVA.


def execute():
	frappe.db.sql(
		"""
		update `tabProject Billing Entry` e
		join `tabSales Invoice` d on d.name = e.reference_name
		set e.billable_amount = d.base_net_total
		where e.is_auto_generated = 1
			and e.reference_doctype = 'Sales Invoice'
			and d.docstatus = 1
			and ifnull(d.project, '') != ''
		"""
	)
