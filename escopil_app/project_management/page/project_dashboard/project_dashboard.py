from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate

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
		select date_format(po.transaction_date, '%%Y-%%m') as month_key,
			sum(item.amount - item.billed_amt) as total
		from `tabPurchase Order` po
		inner join `tabPurchase Order Item` item on item.parent = po.name
		where po.docstatus = 1
			and ifnull(po.buying_mode, '') != 'Petty Cash'
			and item.project = %(project)s
			and item.custom_rubrica is not null and item.custom_rubrica != ''
		group by month_key
		having total > 0
		""",
		{"project": project},
		as_dict=True,
	)
	committed_map = {row.month_key: flt(row.total) for row in committed_rows}

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
		for m in months:
			totals_by_month[m] += flt(row_actuals.get(m))
		rubricas.append({
			"rubrica": r.rubrica,
			"monthly_forecast": flt(r.monthly_forecast),
			"weight": (flt(r.monthly_forecast) / total_forecast) if total_forecast else 0,
			"actuals": {m: flt(row_actuals.get(m)) for m in months},
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
		"committed": {m: flt(committed_map.get(m)) for m in months},
		"billing": {m: flt(billing_map.get(m)) for m in months},
		"billing_forecast": billing_forecast_by_month,
		"margin": margin_by_month,
		"margin_pct": margin_pct_by_month,
	}
