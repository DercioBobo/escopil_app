from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import add_months, flt, fmt_money, get_first_day, get_last_day, getdate

MONTHS_PT = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _month_key(date):
	return getdate(date).strftime("%Y-%m")


def _month_label(month_key):
	year, month = month_key.split("-")
	return "{0}/{1}".format(MONTHS_PT[int(month) - 1], year)


MONTH_NAME_TO_NUM = {name: i + 1 for i, name in enumerate(MONTHS_PT)}


@frappe.whitelist()
def get_dashboard_data(project):
	project_doc = frappe.get_doc("Project", project)

	if not project_doc.expected_start_date or not project_doc.expected_end_date:
		frappe.throw(
			_("Defina a Data de Início Prevista e a Data de Fim Prevista no Projeto para gerar o painel mensal.")
		)

	months = []
	cursor = get_first_day(project_doc.expected_start_date)
	end = get_first_day(project_doc.expected_end_date)
	while cursor <= end:
		months.append(_month_key(cursor))
		cursor = add_months(cursor, 1)

	rubrica_rows = project_doc.get("custom_budget_rubricas") or []
	total_forecast = sum(flt(r.monthly_forecast) for r in rubrica_rows)

	default_billing_forecast = flt(project_doc.custom_monthly_billing_forecast)
	billing_forecast_overrides = {}
	for row in (project_doc.get("custom_billing_forecast_overrides") or []):
		month_num = MONTH_NAME_TO_NUM.get(row.month_name)
		if not month_num or not row.year:
			continue
		billing_forecast_overrides["{0}-{1:02d}".format(int(row.year), month_num)] = flt(row.amount)

	billing_forecast_by_month = {
		m: billing_forecast_overrides.get(m, default_billing_forecast) for m in months
	}

	actuals = frappe.db.sql(
		"""
		select rubrica, date_format(posting_date, '%%Y-%%m') as month_key, sum(amount) as total
		from `tabProject Cost Entry`
		where project = %(project)s
		group by rubrica, month_key
		""",
		{"project": project},
		as_dict=True,
	)
	actuals_map = {}
	for row in actuals:
		actuals_map.setdefault(row.rubrica, {})[row.month_key] = flt(row.total)

	committed_rows = frappe.db.sql(
		"""
		select po.custom_rubrica as rubrica,
			date_format(po.transaction_date, '%%Y-%%m') as month_key,
			sum(po.base_grand_total * (100 - po.per_billed) / 100) as total
		from `tabPurchase Order` po
		where po.docstatus = 1
			and ifnull(po.buying_mode, '') != 'Petty Cash'
			and po.project = %(project)s
			and ifnull(po.custom_rubrica, '') != ''
		group by rubrica, month_key
		having total > 0
		""",
		{"project": project},
		as_dict=True,
	)
	committed_map = {}
	committed_by_month = {m: 0.0 for m in months}
	for row in committed_rows:
		committed_map.setdefault(row.rubrica, {})[row.month_key] = flt(row.total)
		if row.month_key in committed_by_month:
			committed_by_month[row.month_key] += flt(row.total)

	billing_rows = frappe.get_all(
		"Project Billing Entry",
		filters={"project": project},
		fields=["month", "billable_amount"],
	)
	billing_map = {}
	for row in billing_rows:
		month_key = _month_key(row.month)
		billing_map[month_key] = billing_map.get(month_key, 0) + flt(row.billable_amount)

	rubricas = []
	totals_by_month = {m: 0.0 for m in months}
	for r in rubrica_rows:
		row_actuals = actuals_map.get(r.rubrica, {})
		row_committed = committed_map.get(r.rubrica, {})
		for m in months:
			totals_by_month[m] += flt(row_actuals.get(m))
		rubricas.append({
			"rubrica": r.rubrica,
			"monthly_forecast": flt(r.monthly_forecast),
			"weight": (flt(r.monthly_forecast) / total_forecast) if total_forecast else 0,
			"actuals": {m: flt(row_actuals.get(m)) for m in months},
			"committed": {m: flt(row_committed.get(m)) for m in months},
		})

	margin_by_month = {}
	margin_pct_by_month = {}
	for m in months:
		billing = flt(billing_map.get(m))
		margin = billing - totals_by_month[m]
		margin_by_month[m] = margin
		margin_pct_by_month[m] = (margin / billing * 100) if billing else 0

	return {
		"months": [{"key": m, "label": _month_label(m)} for m in months],
		"rubricas": rubricas,
		"total_forecast": total_forecast,
		"totals": totals_by_month,
		"committed": {m: flt(committed_by_month.get(m)) for m in months},
		"billing": {m: flt(billing_map.get(m)) for m in months},
		"billing_forecast": billing_forecast_by_month,
		"margin": margin_by_month,
		"margin_pct": margin_pct_by_month,
	}


@frappe.whitelist()
def get_cell_breakdown(project, kind, month, rubrica=None):
	"""Source documents behind a single dashboard cell, so the value can be
	drilled from the ledger. `month` is any date in the target month; the sum
	of the returned rows reconciles to the cell it was opened from.

	kind:
		cost        — Project Cost Entries for one rubrica in the month
		cost_total  — Project Cost Entries for every budget rubrica in the month
		billing     — Project Billing Entries in the month
		committed   — open (un-billed) Purchase Orders dated in the month
	"""
	frappe.has_permission("Project", "read", doc=project, throw=True)

	first_day = get_first_day(month)
	last_day = get_last_day(first_day)

	if kind == "cost":
		return _cost_breakdown(project, first_day, last_day, rubrica=rubrica)
	if kind == "cost_total":
		budget_rubricas = frappe.get_all(
			"Project Budget Rubrica", filters={"parent": project}, pluck="rubrica"
		)
		return _cost_breakdown(project, first_day, last_day, rubricas=budget_rubricas)
	if kind == "billing":
		return _billing_breakdown(project, first_day, last_day)
	if kind == "committed":
		return _committed_breakdown(project, first_day, last_day, rubrica=rubrica)

	frappe.throw(_("Tipo de detalhe desconhecido: {0}").format(kind))


def _cost_breakdown(project, first_day, last_day, rubrica=None, rubricas=None):
	filters = {"project": project, "posting_date": ["between", [first_day, last_day]]}
	if rubrica:
		filters["rubrica"] = rubrica
	elif rubricas is not None:
		filters["rubrica"] = ["in", rubricas or [""]]

	entries = frappe.get_all(
		"Project Cost Entry",
		filters=filters,
		fields=[
			"posting_date as date", "rubrica", "amount", "source_type as origem",
			"reference_doctype as doctype", "reference_name as docname", "remarks as note",
		],
		order_by="posting_date asc, creation asc",
	)
	return _pack(entries)


def _billing_breakdown(project, first_day, last_day):
	entries = frappe.get_all(
		"Project Billing Entry",
		filters={"project": project, "month": ["between", [first_day, last_day]]},
		fields=[
			"month as date", "billable_amount as amount", "source_type as origem",
			"reference_doctype as doctype", "reference_name as docname", "remarks as note",
		],
		order_by="month asc, creation asc",
	)
	return _pack(entries)


def _committed_breakdown(project, first_day, last_day, rubrica=None):
	conditions = ""
	params = {"project": project, "start": first_day, "end": last_day}
	if rubrica:
		conditions = " and po.custom_rubrica = %(rubrica)s"
		params["rubrica"] = rubrica

	rows = frappe.db.sql(
		"""
		select po.name as docname, po.transaction_date as date,
			po.custom_rubrica as rubrica, po.base_grand_total, po.per_billed
		from `tabPurchase Order` po
		where po.docstatus = 1
			and ifnull(po.buying_mode, '') != 'Petty Cash'
			and po.project = %(project)s
			and ifnull(po.custom_rubrica, '') != ''
			and po.transaction_date between %(start)s and %(end)s
			{conditions}
		order by po.transaction_date asc, po.name asc
		""".format(conditions=conditions),
		params,
		as_dict=True,
	)

	# group by rubrica exactly like the dashboard query (`group by rubrica ...
	# having total > 0`): a rubrica whose open value nets <= 0 for the month is
	# dropped whole, so the modal total reconciles to the cell.
	by_rubrica = {}
	for po in rows:
		remaining = flt(po.base_grand_total) * (100 - flt(po.per_billed)) / 100
		by_rubrica.setdefault(po.rubrica, []).append((po, remaining))

	entries = []
	for items in by_rubrica.values():
		if sum(rem for _, rem in items) <= 0:
			continue
		for po, remaining in items:
			entries.append({
				"date": po.date,
				"rubrica": po.rubrica,
				"amount": remaining,
				"origem": _("Encomenda"),
				"doctype": "Purchase Order",
				"docname": po.docname,
				"note": _("{0} c/ IVA · {1}% faturado").format(
					fmt_money(po.base_grand_total), flt(po.per_billed)
				),
			})

	entries.sort(key=lambda e: (e["date"], e["docname"]))
	return _pack(entries)


def _pack(entries):
	return {"rows": entries, "total": sum(flt(e["amount"]) for e in entries)}
