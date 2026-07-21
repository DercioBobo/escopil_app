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

	billing_rows = frappe.get_all(
		"Project Billing Entry",
		filters={"project": project},
		fields=["month", "billable_amount"],
	)
	billing_map = {}
	for row in billing_rows:
		billing_map[_month_key(row.month)] = flt(row.billable_amount)

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
		"billing": {m: flt(billing_map.get(m)) for m in months},
		"margin": margin_by_month,
		"margin_pct": margin_pct_by_month,
	}
