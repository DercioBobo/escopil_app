from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import (
	add_months,
	cint,
	date_diff,
	flt,
	fmt_money,
	formatdate,
	get_first_day,
	get_last_day,
	getdate,
	nowdate,
)
from escopil_app.project_management.utils import FUEL_RUBRICA

PAGE_SIZE = 20

MONTHS_PT = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _month_range(offset=0):
	first = get_first_day(add_months(nowdate(), offset))
	return first, get_last_day(first)


def _month_label(date):
	d = getdate(date)
	return "{0} de {1}".format(MONTHS_PT[d.month - 1], d.year)


def _month_label_short(date):
	d = getdate(date)
	return "{0}/{1}".format(MONTHS_PT[d.month - 1][:3], str(d.year)[-2:])


def _currency():
	return frappe.defaults.get_global_default("currency") or "MZN"


def _money(amount):
	return fmt_money(flt(amount), currency=_currency())


def _sum_invoices(start, end):
	return flt(frappe.db.sql(
		"""
		select sum(grand_total)
		from `tabSales Invoice`
		where docstatus = 1 and posting_date between %(start)s and %(end)s
		""",
		{"start": start, "end": end},
	)[0][0])


# ---------------------------------------------------------------------------
# Handlers — Faturação (Invoicing)
# ---------------------------------------------------------------------------

def h_total_this_month(**kwargs):
	start, end = _month_range(0)
	row = frappe.db.sql(
		"""
		select
			sum(grand_total) as total,
			sum(grand_total - outstanding_amount) as received,
			sum(outstanding_amount) as outstanding
		from `tabSales Invoice`
		where docstatus = 1 and posting_date between %(start)s and %(end)s
		""",
		{"start": start, "end": end},
		as_dict=True,
	)[0]

	return {
		"title": "Faturação de {0}".format(_month_label(start)),
		"blocks": [
			{
				"type": "kpi_grid",
				"items": [
					{"label": "Faturado", "value": _money(row.total)},
					{"label": "Recebido", "value": _money(row.received)},
					{"label": "Em Aberto", "value": _money(row.outstanding)},
				],
			},
		],
		"follow_ups": [
			{"id": "invoicing_total_vs_last_month", "label": "Comparar com o mês passado"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"},
		],
	}


def h_total_vs_last_month(**kwargs):
	months = [_month_range(offset) for offset in range(-5, 1)]
	totals = [_sum_invoices(start, end) for start, end in months]

	cur_total = totals[-1]
	prev_total = totals[-2]
	delta_pct = ((cur_total - prev_total) / prev_total * 100) if prev_total else None

	return {
		"title": "Faturação: tendência mensal",
		"blocks": [
			{
				"type": "trend",
				"label": "Faturação (últimos 6 meses)",
				"points": [
					{"label": _month_label_short(start), "value": total}
					for (start, _end), total in zip(months, totals)
				],
			},
			{
				"type": "comparison",
				"items": [
					{"label": _month_label(months[-2][0]), "value": _money(prev_total)},
					{"label": _month_label(months[-1][0]), "value": _money(cur_total)},
				],
				"delta_pct": delta_pct,
			},
		],
		"follow_ups": [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
			{"id": "invoicing_annual_comparison", "label": "Comparar faturação anual"},
		],
	}


def h_top_debtors(**kwargs):
	rows = frappe.db.sql(
		"""
		select customer, customer_name,
			sum(outstanding_amount) as outstanding,
			sum(case when due_date < %(today)s then outstanding_amount else 0 end) as overdue
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0
		group by customer
		order by outstanding desc
		limit 10
		""",
		{"today": nowdate()},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Clientes com maior saldo em aberto",
			"blocks": [{"type": "text", "text": "Não há faturas em aberto neste momento."}],
			"follow_ups": [{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"}],
		}

	follow_ups = [
		{"id": "invoicing_overdue_invoices", "label": "Mostrar apenas faturas vencidas"},
		{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
	]
	top = rows[0]
	follow_ups.insert(0, {
		"id": "invoicing_customer_detail",
		"label": "Ver detalhe de {0}".format(top.customer_name or top.customer),
		"params": {"customer": top.customer},
	})

	return {
		"title": "Clientes com maior saldo em aberto",
		"blocks": [
			{
				"type": "bar",
				"items": [
					{
						"label": r.customer_name or r.customer,
						"value": flt(r.outstanding),
						"display": _money(r.outstanding),
					}
					for r in rows[:5]
				],
			},
			{
				"type": "table",
				"columns": ["Cliente", "Valor em Aberto", "Valor Vencido"],
				"rows": [[r.customer_name or r.customer, _money(r.outstanding), _money(r.overdue)] for r in rows],
				"row_prompt_id": "invoicing_customer_detail",
				"row_params": [{"customer": r.customer} for r in rows],
				"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
			},
		],
		"follow_ups": follow_ups,
	}


def h_overdue_invoices(offset=0, **kwargs):
	offset = cint(offset)

	summary = frappe.db.sql(
		"""
		select count(*) as total_count, sum(outstanding_amount) as total_value
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		""",
		{"today": nowdate()},
		as_dict=True,
	)[0]
	total = cint(summary.total_count)
	total_value = flt(summary.total_value)

	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, outstanding_amount as amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		order by due_date asc
		limit %(limit)s offset %(offset)s
		""",
		{"today": nowdate(), "limit": PAGE_SIZE, "offset": offset},
		as_dict=True,
	)

	if not rows:
		text = "Não há mais faturas vencidas para mostrar." if offset else "Não há faturas vencidas neste momento."
		return {
			"title": "Faturas vencidas",
			"blocks": [{"type": "text", "text": text}],
			"follow_ups": [{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"}],
		}

	today = getdate(nowdate())
	shown_upto = offset + len(rows)

	table_block = {
		"type": "table",
		"columns": ["Fatura", "Cliente", "Valor", "Dias em Atraso"],
		"rows": [
			[r.name, r.customer_name or r.customer, _money(r.amount), date_diff(today, r.due_date)]
			for r in rows
		],
		"row_prompt_id": "invoicing_customer_detail",
		"row_params": [{"customer": r.customer} for r in rows],
		"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
		"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
	}

	if shown_upto < total:
		remaining = total - shown_upto
		table_block["load_more"] = {
			"prompt_id": "invoicing_overdue_invoices",
			"label": "Mostrar mais {0}".format(min(PAGE_SIZE, remaining)),
			"params": {"offset": shown_upto},
			"remaining": remaining,
		}

	blocks = [
		{
			"type": "text",
			"text": "A mostrar {0} de {1} faturas vencidas ({2} no total), das mais antigas para as mais recentes.".format(
				shown_upto, total, _money(total_value)
			),
		},
		table_block,
	]

	follow_ups = [
		{"id": "invoicing_aging_report", "label": "Ver por antiguidade de dívida"},
		{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
	]

	return {
		"title": "Faturas vencidas",
		"blocks": blocks,
		"follow_ups": follow_ups,
	}


def h_customer_detail(customer=None, **kwargs):
	if not customer:
		frappe.throw(_("Cliente não especificado."))

	customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

	summary = frappe.db.sql(
		"""
		select
			sum(grand_total) as total,
			sum(outstanding_amount) as outstanding,
			sum(case when due_date < %(today)s then outstanding_amount else 0 end) as overdue,
			count(*) as invoice_count
		from `tabSales Invoice`
		where docstatus = 1 and customer = %(customer)s
		""",
		{"customer": customer, "today": nowdate()},
		as_dict=True,
	)[0]

	blocks = [
		{
			"type": "kpi_grid",
			"items": [
				{"label": "Total Faturado", "value": _money(summary.total)},
				{"label": "Em Aberto", "value": _money(summary.outstanding)},
				{"label": "Vencido", "value": _money(summary.overdue)},
				{"label": "Nº Faturas", "value": str(cint(summary.invoice_count))},
			],
		},
	]

	if cint(summary.invoice_count):
		open_rows = frappe.db.sql(
			"""
			select name, posting_date, grand_total, outstanding_amount, due_date
			from `tabSales Invoice`
			where docstatus = 1 and customer = %(customer)s and outstanding_amount > 0
			order by due_date asc
			""",
			{"customer": customer},
			as_dict=True,
		)

		if open_rows:
			today = getdate(nowdate())
			blocks.append({
				"type": "table",
				"columns": ["Fatura", "Data", "Valor", "Vencimento", "Estado"],
				"rows": [
					[
						r.name,
						formatdate(r.posting_date, "dd/MM/yyyy"),
						_money(r.grand_total),
						formatdate(r.due_date, "dd/MM/yyyy"),
						"Vencida" if getdate(r.due_date) < today else "Em dia",
					]
					for r in open_rows
				],
				"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in open_rows]},
			})
		else:
			blocks.append({"type": "text", "text": "Sem faturas em aberto."})
	else:
		blocks.append({"type": "text", "text": "{0} ainda não tem faturas submetidas.".format(customer_name)})

	return {
		"title": "Visão geral de {0}".format(customer_name),
		"blocks": blocks,
		"follow_ups": [
			{
				"id": "invoicing_customer_trend_comparison",
				"label": "Comparar com o mês passado",
				"params": {"customer": customer},
			},
			{
				"id": "invoicing_customer_all_invoices",
				"label": "Ver todo o histórico de faturas",
				"params": {"customer": customer},
			},
		],
	}


def h_customer_trend_comparison(customer=None, **kwargs):
	if not customer:
		frappe.throw(_("Cliente não especificado."))

	customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

	months = [_month_range(offset) for offset in range(-5, 1)]
	totals = []
	for start, end in months:
		totals.append(flt(frappe.db.sql(
			"""
			select sum(grand_total)
			from `tabSales Invoice`
			where docstatus = 1 and customer = %(customer)s and posting_date between %(start)s and %(end)s
			""",
			{"customer": customer, "start": start, "end": end},
		)[0][0]))

	cur_total = totals[-1]
	prev_total = totals[-2]
	delta_pct = ((cur_total - prev_total) / prev_total * 100) if prev_total else None

	return {
		"title": "Faturação de {0}: tendência mensal".format(customer_name),
		"blocks": [
			{
				"type": "trend",
				"label": "Faturação (últimos 6 meses)",
				"points": [
					{"label": _month_label_short(start), "value": total}
					for (start, _end), total in zip(months, totals)
				],
			},
			{
				"type": "comparison",
				"items": [
					{"label": _month_label(months[-2][0]), "value": _money(prev_total)},
					{"label": _month_label(months[-1][0]), "value": _money(cur_total)},
				],
				"delta_pct": delta_pct,
			},
		],
		"follow_ups": [
			{
				"id": "invoicing_customer_all_invoices",
				"label": "Ver todo o histórico de faturas",
				"params": {"customer": customer},
			},
		],
	}


def h_customer_all_invoices(customer=None, offset=0, **kwargs):
	if not customer:
		frappe.throw(_("Cliente não especificado."))

	offset = cint(offset)
	customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

	total = cint(frappe.db.sql(
		"""select count(*) from `tabSales Invoice` where docstatus = 1 and customer = %(customer)s""",
		{"customer": customer},
	)[0][0])

	rows = frappe.db.sql(
		"""
		select name, posting_date, grand_total, outstanding_amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and customer = %(customer)s
		order by posting_date desc
		limit %(limit)s offset %(offset)s
		""",
		{"customer": customer, "limit": PAGE_SIZE, "offset": offset},
		as_dict=True,
	)

	if not rows:
		text = (
			"Não há mais faturas para mostrar." if offset
			else "{0} ainda não tem faturas submetidas.".format(customer_name)
		)
		return {
			"title": "Histórico de faturas de {0}".format(customer_name),
			"blocks": [{"type": "text", "text": text}],
			"follow_ups": [],
		}

	today = getdate(nowdate())
	shown_upto = offset + len(rows)

	def _status(r):
		if flt(r.outstanding_amount) <= 0:
			return "Paga"
		return "Vencida" if getdate(r.due_date) < today else "Em dia"

	table_block = {
		"type": "table",
		"columns": ["Fatura", "Data", "Valor", "Estado"],
		"rows": [
			[r.name, formatdate(r.posting_date, "dd/MM/yyyy"), _money(r.grand_total), _status(r)]
			for r in rows
		],
		"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
	}

	if shown_upto < total:
		remaining = total - shown_upto
		table_block["load_more"] = {
			"prompt_id": "invoicing_customer_all_invoices",
			"label": "Mostrar mais {0}".format(min(PAGE_SIZE, remaining)),
			"params": {"customer": customer, "offset": shown_upto},
			"remaining": remaining,
		}

	return {
		"title": "Histórico de faturas de {0} ({1} de {2})".format(customer_name, shown_upto, total),
		"blocks": [table_block],
		"follow_ups": [],
	}


def h_total_this_year(**kwargs):
	year = getdate(nowdate()).year
	start = getdate("{0}-01-01".format(year))
	end = getdate(nowdate())

	row = frappe.db.sql(
		"""
		select
			sum(grand_total) as total,
			sum(grand_total - outstanding_amount) as received,
			sum(outstanding_amount) as outstanding,
			count(*) as invoice_count
		from `tabSales Invoice`
		where docstatus = 1 and posting_date between %(start)s and %(end)s
		""",
		{"start": start, "end": end},
		as_dict=True,
	)[0]

	months_elapsed = getdate(nowdate()).month
	average_monthly = flt(row.total) / months_elapsed if months_elapsed else 0

	return {
		"title": "Faturação de {0}".format(year),
		"blocks": [
			{
				"type": "kpi_grid",
				"items": [
					{"label": "Faturado", "value": _money(row.total)},
					{"label": "Recebido", "value": _money(row.received)},
					{"label": "Em Aberto", "value": _money(row.outstanding)},
					{"label": "Nº Faturas", "value": str(cint(row.invoice_count))},
					{"label": "Média Mensal", "value": _money(average_monthly)},
				],
			},
		],
		"follow_ups": [
			{"id": "invoicing_annual_comparison", "label": "Comparar com o ano passado"},
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
			{"id": "invoicing_best_month", "label": "Qual foi o nosso melhor mês este ano?"},
		],
	}


def h_annual_comparison(**kwargs):
	this_year = getdate(nowdate()).year
	last_year = this_year - 1

	rows = frappe.db.sql(
		"""
		select year(posting_date) as yr, month(posting_date) as mo, sum(grand_total) as total
		from `tabSales Invoice`
		where docstatus = 1 and year(posting_date) in (%(this_year)s, %(last_year)s)
		group by yr, mo
		""",
		{"this_year": this_year, "last_year": last_year},
		as_dict=True,
	)

	totals = {this_year: [0] * 12, last_year: [0] * 12}
	for r in rows:
		if r.yr in totals:
			totals[r.yr][r.mo - 1] = flt(r.total)

	month_labels = [m[:3] for m in MONTHS_PT]
	cur_total = sum(totals[this_year])
	prev_total = sum(totals[last_year])
	delta_pct = ((cur_total - prev_total) / prev_total * 100) if prev_total else None

	return {
		"title": "Faturação anual: {0} vs {1}".format(this_year, last_year),
		"blocks": [
			{
				"type": "trend",
				"label": "Faturação por mês",
				"series": [
					{
						"label": str(this_year),
						"points": [
							{"label": label, "value": value}
							for label, value in zip(month_labels, totals[this_year])
						],
					},
					{
						"label": str(last_year),
						"points": [
							{"label": label, "value": value}
							for label, value in zip(month_labels, totals[last_year])
						],
					},
				],
			},
			{
				"type": "comparison",
				"items": [
					{"label": str(last_year), "value": _money(prev_total)},
					{"label": str(this_year), "value": _money(cur_total)},
				],
				"delta_pct": delta_pct,
			},
		],
		"follow_ups": [
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
			{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"},
		],
	}


def _top_customers(start=None, end=None, limit=10):
	conditions = "docstatus = 1"
	values = {}
	if start and end:
		conditions += " and posting_date between %(start)s and %(end)s"
		values.update({"start": start, "end": end})

	return frappe.db.sql(
		"""
		select customer, customer_name, sum(grand_total) as total, count(*) as invoice_count
		from `tabSales Invoice`
		where {conditions}
		group by customer
		order by total desc
		limit %(limit)s
		""".format(conditions=conditions),
		dict(values, limit=limit),
		as_dict=True,
	)


def _top_customers_response(rows, title, scope_follow_ups):
	if not rows:
		return {
			"title": title,
			"blocks": [{"type": "text", "text": "Não há faturas submetidas neste período."}],
			"follow_ups": [{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"}],
		}

	return {
		"title": title,
		"blocks": [
			{
				"type": "bar",
				"items": [
					{
						"label": r.customer_name or r.customer,
						"value": flt(r.total),
						"display": _money(r.total),
					}
					for r in rows[:5]
				],
			},
			{
				"type": "table",
				"columns": ["Cliente", "Total Faturado", "Nº Faturas"],
				"rows": [
					[r.customer_name or r.customer, _money(r.total), cint(r.invoice_count)]
					for r in rows
				],
				"row_prompt_id": "invoicing_customer_detail",
				"row_params": [{"customer": r.customer} for r in rows],
				"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
			},
		],
		"follow_ups": scope_follow_ups + [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		],
	}


def h_top_customers_month(**kwargs):
	start, end = _month_range(0)
	rows = _top_customers(start, end)
	return _top_customers_response(
		rows,
		"Maiores clientes em {0}".format(_month_label(start)),
		[
			{"id": "invoicing_top_customers_year", "label": "Ver este ano"},
			{"id": "invoicing_top_customers_alltime", "label": "Ver desde sempre"},
		],
	)


def h_top_customers_year(**kwargs):
	year = getdate(nowdate()).year
	start = getdate("{0}-01-01".format(year))
	end = getdate(nowdate())
	rows = _top_customers(start, end)
	return _top_customers_response(
		rows,
		"Maiores clientes em {0}".format(year),
		[
			{"id": "invoicing_top_customers_month", "label": "Ver apenas este mês"},
			{"id": "invoicing_top_customers_alltime", "label": "Ver desde sempre"},
		],
	)


def h_top_customers_alltime(**kwargs):
	rows = _top_customers()
	return _top_customers_response(
		rows,
		"Maiores clientes (desde sempre)",
		[
			{"id": "invoicing_top_customers_month", "label": "Ver apenas este mês"},
			{"id": "invoicing_top_customers_year", "label": "Ver apenas este ano"},
		],
	)


def h_top_invoices_month(**kwargs):
	start, end = _month_range(0)
	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, grand_total, posting_date
		from `tabSales Invoice`
		where docstatus = 1 and posting_date between %(start)s and %(end)s
		order by grand_total desc
		limit 10
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Maiores faturas de {0}".format(_month_label(start)),
			"blocks": [{"type": "text", "text": "Não há faturas submetidas este mês."}],
			"follow_ups": [{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"}],
		}

	return {
		"title": "Maiores faturas de {0}".format(_month_label(start)),
		"blocks": [{
			"type": "table",
			"columns": ["Fatura", "Cliente", "Valor", "Data"],
			"rows": [
				[r.name, r.customer_name or r.customer, _money(r.grand_total), formatdate(r.posting_date, "dd/MM/yyyy")]
				for r in rows
			],
			"row_prompt_id": "invoicing_customer_detail",
			"row_params": [{"customer": r.customer} for r in rows],
			"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
			"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
		}],
		"follow_ups": [
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
			{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
		],
	}


def h_outstanding_total(**kwargs):
	total = flt(frappe.db.sql(
		"""
		select sum(outstanding_amount)
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0
		"""
	)[0][0])

	return {
		"title": "Total por Receber",
		"blocks": [
			{"type": "metric", "label": "Valor em Aberto", "value": _money(total)},
		],
		"follow_ups": [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_aging_report", "label": "Ver por antiguidade de dívida"},
		],
	}


def h_aging_report(**kwargs):
	today = getdate(nowdate())
	rows = frappe.db.sql(
		"""
		select outstanding_amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		""",
		{"today": today},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Faturas vencidas por antiguidade",
			"blocks": [{"type": "text", "text": "Não há faturas vencidas neste momento."}],
			"follow_ups": [{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"}],
		}

	buckets = {"0-30 dias": 0.0, "31-60 dias": 0.0, "61-90 dias": 0.0, "Mais de 90 dias": 0.0}
	for r in rows:
		days = date_diff(today, r.due_date)
		amount = flt(r.outstanding_amount)
		if days <= 30:
			buckets["0-30 dias"] += amount
		elif days <= 60:
			buckets["31-60 dias"] += amount
		elif days <= 90:
			buckets["61-90 dias"] += amount
		else:
			buckets["Mais de 90 dias"] += amount

	total_overdue = sum(buckets.values())

	return {
		"title": "Faturas vencidas por antiguidade",
		"blocks": [
			{"type": "metric", "label": "Total Vencido", "value": _money(total_overdue)},
			{
				"type": "bar",
				"items": [
					{"label": label, "value": amount, "display": _money(amount)}
					for label, amount in buckets.items()
				],
			},
		],
		"follow_ups": [
			{"id": "invoicing_overdue_invoices", "label": "Ver lista de faturas vencidas"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		],
	}


def h_recent_invoices(**kwargs):
	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, grand_total, posting_date
		from `tabSales Invoice`
		where docstatus = 1
		order by posting_date desc, creation desc
		limit 10
		""",
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Faturas mais recentes",
			"blocks": [{"type": "text", "text": "Ainda não há faturas submetidas."}],
			"follow_ups": [{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"}],
		}

	return {
		"title": "Faturas mais recentes",
		"blocks": [{
			"type": "table",
			"columns": ["Fatura", "Cliente", "Valor", "Data"],
			"rows": [
				[r.name, r.customer_name or r.customer, _money(r.grand_total), formatdate(r.posting_date, "dd/MM/yyyy")]
				for r in rows
			],
			"row_prompt_id": "invoicing_customer_detail",
			"row_params": [{"customer": r.customer} for r in rows],
			"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
			"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
		}],
		"follow_ups": [
			{"id": "invoicing_top_invoices_month", "label": "Quais as maiores faturas emitidas este mês?"},
			{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
		],
	}


def h_unpaid_invoices(offset=0, **kwargs):
	offset = cint(offset)

	summary = frappe.db.sql(
		"""
		select count(*) as total_count, sum(outstanding_amount) as total_value
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0
		""",
		as_dict=True,
	)[0]
	total = cint(summary.total_count)
	total_value = flt(summary.total_value)

	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, outstanding_amount as amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0
		order by due_date asc
		limit %(limit)s offset %(offset)s
		""",
		{"limit": PAGE_SIZE, "offset": offset},
		as_dict=True,
	)

	if not rows:
		text = "Não há mais faturas para mostrar." if offset else "Não há faturas por pagar neste momento."
		return {
			"title": "Faturas por pagar",
			"blocks": [{"type": "text", "text": text}],
			"follow_ups": [{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"}],
		}

	today = getdate(nowdate())
	shown_upto = offset + len(rows)

	table_block = {
		"type": "table",
		"columns": ["Fatura", "Cliente", "Valor", "Vencimento"],
		"rows": [
			[
				r.name,
				r.customer_name or r.customer,
				_money(r.amount),
				"Vencida" if getdate(r.due_date) < today else formatdate(r.due_date, "dd/MM/yyyy"),
			]
			for r in rows
		],
		"row_prompt_id": "invoicing_customer_detail",
		"row_params": [{"customer": r.customer} for r in rows],
		"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
		"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
	}

	if shown_upto < total:
		remaining = total - shown_upto
		table_block["load_more"] = {
			"prompt_id": "invoicing_unpaid_invoices",
			"label": "Mostrar mais {0}".format(min(PAGE_SIZE, remaining)),
			"params": {"offset": shown_upto},
			"remaining": remaining,
		}

	return {
		"title": "Faturas por pagar",
		"blocks": [
			{
				"type": "text",
				"text": "A mostrar {0} de {1} faturas por pagar ({2} no total).".format(
					shown_upto, total, _money(total_value)
				),
			},
			table_block,
		],
		"follow_ups": [
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
			{"id": "invoicing_partially_paid", "label": "Quais faturas estão parcialmente pagas?"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		],
	}


def h_partially_paid(**kwargs):
	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, grand_total, outstanding_amount
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and outstanding_amount < grand_total
		order by outstanding_amount desc
		limit 20
		""",
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Faturas parcialmente pagas",
			"blocks": [{"type": "text", "text": "Não há faturas parcialmente pagas neste momento."}],
			"follow_ups": [{"id": "invoicing_unpaid_invoices", "label": "Quais faturas ainda não foram pagas?"}],
		}

	return {
		"title": "Faturas parcialmente pagas",
		"blocks": [{
			"type": "table",
			"columns": ["Fatura", "Cliente", "Valor Total", "Ainda em Aberto"],
			"rows": [
				[r.name, r.customer_name or r.customer, _money(r.grand_total), _money(r.outstanding_amount)]
				for r in rows
			],
			"row_prompt_id": "invoicing_customer_detail",
			"row_params": [{"customer": r.customer} for r in rows],
			"row_labels": ["Ver detalhe de {0}".format(r.customer_name or r.customer) for r in rows],
			"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
		}],
		"follow_ups": [
			{"id": "invoicing_unpaid_invoices", "label": "Quais faturas ainda não foram pagas?"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		],
	}


def h_best_month(**kwargs):
	year = getdate(nowdate()).year
	rows = frappe.db.sql(
		"""
		select month(posting_date) as mo, sum(grand_total) as total
		from `tabSales Invoice`
		where docstatus = 1 and year(posting_date) = %(year)s
		group by mo
		""",
		{"year": year},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Melhor mês de {0}".format(year),
			"blocks": [{"type": "text", "text": "Ainda não há faturas submetidas este ano."}],
			"follow_ups": [{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"}],
		}

	best = max(rows, key=lambda r: flt(r.total))
	best_label = MONTHS_PT[best.mo - 1]

	return {
		"title": "Melhor mês de {0}".format(year),
		"blocks": [
			{"type": "metric", "label": "{0} de {1}".format(best_label, year), "value": _money(best.total)},
		],
		"follow_ups": [
			{"id": "invoicing_annual_comparison", "label": "Comparar faturação anual"},
			{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"},
		],
	}


# ---------------------------------------------------------------------------
# Handlers — Projetos (Projects)
# ---------------------------------------------------------------------------

def h_projects_cost_by_project_month(**kwargs):
	start, end = _month_range(0)
	rows = frappe.db.sql(
		"""
		select pce.project, p.project_name, sum(pce.amount) as total
		from `tabProject Cost Entry` pce
		inner join `tabProject` p on p.name = pce.project
		where pce.posting_date between %(start)s and %(end)s
		group by pce.project
		order by total desc
		limit 10
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Custos por projeto em {0}".format(_month_label(start)),
			"blocks": [{"type": "text", "text": "Não há custos lançados este mês."}],
			"follow_ups": [{"id": "projects_top_rubricas_month", "label": "Quais as rubricas mais usadas este mês?"}],
		}

	return {
		"title": "Custos por projeto em {0}".format(_month_label(start)),
		"blocks": [
			{
				"type": "bar",
				"items": [
					{"label": r.project_name or r.project, "value": flt(r.total), "display": _money(r.total)}
					for r in rows[:5]
				],
			},
			{
				"type": "table",
				"columns": ["Projeto", "Custo Total"],
				"rows": [[r.project_name or r.project, _money(r.total)] for r in rows],
				"row_prompt_id": "projects_detail",
				"row_params": [{"project": r.project} for r in rows],
				"row_labels": ["Ver detalhe de {0}".format(r.project_name or r.project) for r in rows],
			},
		],
		"follow_ups": [
			{"id": "projects_margin_by_project_month", "label": "Qual a margem de faturação por projeto este mês?"},
			{"id": "projects_top_rubricas_month", "label": "Quais as rubricas mais usadas este mês?"},
		],
	}


def h_projects_margin_by_project_month(**kwargs):
	start, end = _month_range(0)

	cost_rows = frappe.db.sql(
		"""
		select project, sum(amount) as total
		from `tabProject Cost Entry`
		where posting_date between %(start)s and %(end)s
		group by project
		""",
		{"start": start, "end": end},
		as_dict=True,
	)
	billing_rows = frappe.db.sql(
		"""
		select project, sum(billable_amount) as total
		from `tabProject Billing Entry`
		where month between %(start)s and %(end)s
		group by project
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	cost_map = {r.project: flt(r.total) for r in cost_rows}
	billing_map = {r.project: flt(r.total) for r in billing_rows}
	project_ids = set(cost_map) | set(billing_map)

	if not project_ids:
		return {
			"title": "Margem por projeto em {0}".format(_month_label(start)),
			"blocks": [{"type": "text", "text": "Não há custos ou faturação lançados este mês."}],
			"follow_ups": [{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"}],
		}

	name_map = {
		p.name: p.project_name or p.name
		for p in frappe.get_all("Project", filters={"name": ["in", list(project_ids)]}, fields=["name", "project_name"])
	}

	rows = []
	for project in project_ids:
		billing = billing_map.get(project, 0)
		cost = cost_map.get(project, 0)
		rows.append({
			"project": project,
			"project_name": name_map.get(project, project),
			"billing": billing,
			"cost": cost,
			"margin": billing - cost,
		})
	rows.sort(key=lambda r: r["margin"])

	return {
		"title": "Margem por projeto em {0}".format(_month_label(start)),
		"blocks": [{
			"type": "table",
			"columns": ["Projeto", "Faturação", "Custo", "Margem"],
			"rows": [
				[r["project_name"], _money(r["billing"]), _money(r["cost"]), _money(r["margin"])]
				for r in rows
			],
			"row_prompt_id": "projects_detail",
			"row_params": [{"project": r["project"]} for r in rows],
			"row_labels": ["Ver detalhe de {0}".format(r["project_name"]) for r in rows],
		}],
		"follow_ups": [
			{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"},
			{"id": "projects_billing_by_project_year", "label": "Quanto faturámos por projeto este ano?"},
		],
	}


def h_projects_top_rubricas_month(**kwargs):
	start, end = _month_range(0)
	rows = frappe.db.sql(
		"""
		select rubrica, sum(amount) as total
		from `tabProject Cost Entry`
		where posting_date between %(start)s and %(end)s
		group by rubrica
		order by total desc
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Rubricas mais usadas em {0}".format(_month_label(start)),
			"blocks": [{"type": "text", "text": "Não há custos lançados este mês."}],
			"follow_ups": [{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"}],
		}

	return {
		"title": "Rubricas mais usadas em {0}".format(_month_label(start)),
		"blocks": [{
			"type": "bar",
			"items": [
				{"label": r.rubrica, "value": flt(r.total), "display": _money(r.total)}
				for r in rows
			],
		}],
		"follow_ups": [
			{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"},
			{"id": "projects_fuel_this_month", "label": "Quanto gastámos em Combustível este mês?"},
		],
	}


def h_projects_fuel_this_month(**kwargs):
	start, end = _month_range(0)
	total = flt(frappe.db.sql(
		"""
		select sum(amount)
		from `tabProject Cost Entry`
		where posting_date between %(start)s and %(end)s and rubrica = %(rubrica)s
		""",
		{"start": start, "end": end, "rubrica": FUEL_RUBRICA},
	)[0][0])

	return {
		"title": "Combustível em {0}".format(_month_label(start)),
		"blocks": [
			{"type": "metric", "label": "Total em Combustível", "value": _money(total)},
		],
		"follow_ups": [
			{"id": "projects_top_rubricas_month", "label": "Quais as rubricas mais usadas este mês?"},
			{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"},
		],
	}


def h_projects_over_budget(**kwargs):
	start, end = _month_range(0)

	projects = frappe.get_all(
		"Project",
		filters={"custom_cost_control_enabled": 1},
		fields=["name", "project_name"],
	)
	if not projects:
		return {
			"title": "Projetos a exceder o orçamento",
			"blocks": [{"type": "text", "text": "Não há projetos com Controlo de Custos ativado."}],
			"follow_ups": [{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"}],
		}

	project_names = [p.name for p in projects]

	forecast_rows = frappe.db.sql(
		"""
		select parent as project, sum(monthly_forecast) as total
		from `tabProject Budget Rubrica`
		where parent in %(projects)s
		group by parent
		""",
		{"projects": project_names},
		as_dict=True,
	)
	forecast_map = {r.project: flt(r.total) for r in forecast_rows}

	cost_rows = frappe.db.sql(
		"""
		select project, sum(amount) as total
		from `tabProject Cost Entry`
		where project in %(projects)s and posting_date between %(start)s and %(end)s
		group by project
		""",
		{"projects": project_names, "start": start, "end": end},
		as_dict=True,
	)
	cost_map = {r.project: flt(r.total) for r in cost_rows}

	over = []
	for p in projects:
		forecast = forecast_map.get(p.name, 0)
		actual = cost_map.get(p.name, 0)
		if forecast and actual > forecast:
			over.append({
				"project": p.name,
				"project_name": p.project_name or p.name,
				"forecast": forecast,
				"actual": actual,
				"over_pct": (actual - forecast) / forecast * 100,
			})

	if not over:
		return {
			"title": "Projetos a exceder o orçamento em {0}".format(_month_label(start)),
			"blocks": [{"type": "text", "text": "Nenhum projeto excedeu o orçamento mensal previsto este mês."}],
			"follow_ups": [{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"}],
		}

	over.sort(key=lambda r: r["over_pct"], reverse=True)

	return {
		"title": "Projetos a exceder o orçamento em {0}".format(_month_label(start)),
		"blocks": [{
			"type": "table",
			"columns": ["Projeto", "Orçamento Mensal", "Gasto Real", "Desvio"],
			"rows": [
				[r["project_name"], _money(r["forecast"]), _money(r["actual"]), "+{0:.0f}%".format(r["over_pct"])]
				for r in over
			],
			"row_prompt_id": "projects_detail",
			"row_params": [{"project": r["project"]} for r in over],
			"row_labels": ["Ver detalhe de {0}".format(r["project_name"]) for r in over],
		}],
		"follow_ups": [
			{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"},
			{"id": "projects_margin_by_project_month", "label": "Qual a margem de faturação por projeto este mês?"},
		],
	}


def h_projects_billing_by_project_year(**kwargs):
	year = getdate(nowdate()).year
	start = getdate("{0}-01-01".format(year))
	end = getdate(nowdate())

	rows = frappe.db.sql(
		"""
		select pbe.project, p.project_name, sum(pbe.billable_amount) as total
		from `tabProject Billing Entry` pbe
		inner join `tabProject` p on p.name = pbe.project
		where pbe.month between %(start)s and %(end)s
		group by pbe.project
		order by total desc
		limit 10
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Faturação por projeto em {0}".format(year),
			"blocks": [{"type": "text", "text": "Não há faturação por projeto lançada este ano."}],
			"follow_ups": [{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"}],
		}

	return {
		"title": "Faturação por projeto em {0}".format(year),
		"blocks": [
			{
				"type": "bar",
				"items": [
					{"label": r.project_name or r.project, "value": flt(r.total), "display": _money(r.total)}
					for r in rows[:5]
				],
			},
			{
				"type": "table",
				"columns": ["Projeto", "Faturação"],
				"rows": [[r.project_name or r.project, _money(r.total)] for r in rows],
				"row_prompt_id": "projects_detail",
				"row_params": [{"project": r.project} for r in rows],
				"row_labels": ["Ver detalhe de {0}".format(r.project_name or r.project) for r in rows],
			},
		],
		"follow_ups": [
			{"id": "projects_margin_by_project_month", "label": "Qual a margem de faturação por projeto este mês?"},
		],
	}


def h_projects_detail(project=None, **kwargs):
	if not project:
		frappe.throw(_("Projeto não especificado."))

	project_name = frappe.db.get_value("Project", project, "project_name") or project

	cost_total = flt(frappe.db.sql(
		"""select sum(amount) from `tabProject Cost Entry` where project = %(project)s""",
		{"project": project},
	)[0][0])

	billing_total = flt(frappe.db.sql(
		"""select sum(billable_amount) from `tabProject Billing Entry` where project = %(project)s""",
		{"project": project},
	)[0][0])

	rubrica_rows = frappe.db.sql(
		"""
		select rubrica, sum(amount) as total
		from `tabProject Cost Entry`
		where project = %(project)s
		group by rubrica
		order by total desc
		limit 5
		""",
		{"project": project},
		as_dict=True,
	)

	blocks = [
		{
			"type": "kpi_grid",
			"items": [
				{"label": "Custo Total", "value": _money(cost_total)},
				{"label": "Faturação Total", "value": _money(billing_total)},
				{"label": "Margem", "value": _money(billing_total - cost_total)},
			],
		},
	]

	if rubrica_rows:
		blocks.append({
			"type": "bar",
			"items": [
				{"label": r.rubrica, "value": flt(r.total), "display": _money(r.total)}
				for r in rubrica_rows
			],
		})
	else:
		blocks.append({"type": "text", "text": "Ainda não há custos lançados para este projeto."})

	return {
		"title": "Visão geral de {0}".format(project_name),
		"blocks": blocks,
		"follow_ups": [
			{
				"id": "projects_trend_comparison",
				"label": "Comparar com o mês passado",
				"params": {"project": project},
			},
		],
	}


def h_projects_trend_comparison(project=None, **kwargs):
	if not project:
		frappe.throw(_("Projeto não especificado."))

	project_name = frappe.db.get_value("Project", project, "project_name") or project

	months = [_month_range(offset) for offset in range(-5, 1)]
	cost_totals = []
	billing_totals = []
	for start, end in months:
		cost_totals.append(flt(frappe.db.sql(
			"""
			select sum(amount) from `tabProject Cost Entry`
			where project = %(project)s and posting_date between %(start)s and %(end)s
			""",
			{"project": project, "start": start, "end": end},
		)[0][0]))
		billing_totals.append(flt(frappe.db.sql(
			"""
			select sum(billable_amount) from `tabProject Billing Entry`
			where project = %(project)s and month between %(start)s and %(end)s
			""",
			{"project": project, "start": start, "end": end},
		)[0][0]))

	cur_margin = billing_totals[-1] - cost_totals[-1]
	prev_margin = billing_totals[-2] - cost_totals[-2]
	delta_pct = ((cur_margin - prev_margin) / abs(prev_margin) * 100) if prev_margin else None

	return {
		"title": "{0}: tendência mensal".format(project_name),
		"blocks": [
			{
				"type": "trend",
				"label": "Custo vs Faturação (últimos 6 meses)",
				"series": [
					{
						"label": "Faturação",
						"points": [
							{"label": _month_label_short(start), "value": value}
							for (start, _end), value in zip(months, billing_totals)
						],
					},
					{
						"label": "Custo",
						"points": [
							{"label": _month_label_short(start), "value": value}
							for (start, _end), value in zip(months, cost_totals)
						],
					},
				],
			},
			{
				"type": "comparison",
				"items": [
					{"label": "{0} (margem)".format(_month_label(months[-2][0])), "value": _money(prev_margin)},
					{"label": "{0} (margem)".format(_month_label(months[-1][0])), "value": _money(cur_margin)},
				],
				"delta_pct": delta_pct,
			},
		],
		"follow_ups": [],
	}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SECTIONS = [
	{
		"id": "invoicing",
		"label": "Faturação",
		"prompts": [
			{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
			{"id": "invoicing_outstanding_total", "label": "Quanto temos por receber?"},
			{"id": "invoicing_total_vs_last_month", "label": "Quanto faturámos este mês vs mês passado?"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
			{"id": "invoicing_aging_report", "label": "Qual o valor vencido por antiguidade?"},
			{"id": "invoicing_recent_invoices", "label": "Quais são as faturas mais recentes?"},
			{"id": "invoicing_unpaid_invoices", "label": "Quais faturas ainda não foram pagas?"},
			{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"},
			{"id": "invoicing_annual_comparison", "label": "Comparar faturação anual (este ano vs ano passado)"},
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
			{"id": "invoicing_top_customers_alltime", "label": "Quais são os maiores clientes de sempre?"},
			{"id": "invoicing_top_invoices_month", "label": "Quais as maiores faturas emitidas este mês?"},
		],
	},
	{
		"id": "projects",
		"label": "Projetos",
		"prompts": [
			{"id": "projects_cost_by_project_month", "label": "Quanto gastámos por projeto este mês?"},
			{"id": "projects_margin_by_project_month", "label": "Qual a margem de faturação por projeto este mês?"},
			{"id": "projects_top_rubricas_month", "label": "Quais as rubricas mais usadas este mês?"},
			{"id": "projects_fuel_this_month", "label": "Quanto gastámos em Combustível este mês?"},
			{"id": "projects_over_budget", "label": "Que projetos estão a exceder o orçamento?"},
			{"id": "projects_billing_by_project_year", "label": "Quanto faturámos por projeto este ano?"},
		],
	},
]

HANDLERS = {
	"invoicing_total_this_month": (h_total_this_month, "Sales Invoice"),
	"invoicing_total_vs_last_month": (h_total_vs_last_month, "Sales Invoice"),
	"invoicing_top_debtors": (h_top_debtors, "Sales Invoice"),
	"invoicing_overdue_invoices": (h_overdue_invoices, "Sales Invoice"),
	"invoicing_customer_detail": (h_customer_detail, "Sales Invoice"),
	"invoicing_customer_trend_comparison": (h_customer_trend_comparison, "Sales Invoice"),
	"invoicing_customer_all_invoices": (h_customer_all_invoices, "Sales Invoice"),
	"invoicing_total_this_year": (h_total_this_year, "Sales Invoice"),
	"invoicing_annual_comparison": (h_annual_comparison, "Sales Invoice"),
	"invoicing_top_customers_year": (h_top_customers_year, "Sales Invoice"),
	"invoicing_top_customers_alltime": (h_top_customers_alltime, "Sales Invoice"),
	"invoicing_top_customers_month": (h_top_customers_month, "Sales Invoice"),
	"invoicing_top_invoices_month": (h_top_invoices_month, "Sales Invoice"),
	"invoicing_outstanding_total": (h_outstanding_total, "Sales Invoice"),
	"invoicing_aging_report": (h_aging_report, "Sales Invoice"),
	"invoicing_recent_invoices": (h_recent_invoices, "Sales Invoice"),
	"invoicing_unpaid_invoices": (h_unpaid_invoices, "Sales Invoice"),
	"invoicing_partially_paid": (h_partially_paid, "Sales Invoice"),
	"invoicing_best_month": (h_best_month, "Sales Invoice"),
	"projects_cost_by_project_month": (h_projects_cost_by_project_month, "Project"),
	"projects_margin_by_project_month": (h_projects_margin_by_project_month, "Project"),
	"projects_top_rubricas_month": (h_projects_top_rubricas_month, "Project"),
	"projects_fuel_this_month": (h_projects_fuel_this_month, "Project"),
	"projects_over_budget": (h_projects_over_budget, "Project"),
	"projects_billing_by_project_year": (h_projects_billing_by_project_year, "Project"),
	"projects_detail": (h_projects_detail, "Project"),
	"projects_trend_comparison": (h_projects_trend_comparison, "Project"),
}

PROMPT_LABELS = {p["id"]: p["label"] for section in SECTIONS for p in section["prompts"]}

# Per-section live search: typing a name in the input box resolves straight to
# a detail prompt instead of only matching the fixed suggestion labels. Adding
# a new section's lookup (Purchasing -> Supplier, Projects -> Project, ...)
# is just another entry here — no other plumbing needed.
SEARCH_CONFIG = {
	"invoicing": {
		"doctype": "Customer",
		"search_field": "customer_name",
		"prompt_id": "invoicing_customer_detail",
		"param_key": "customer",
		"result_label": "Ver detalhe de {0}",
		"extra_filters": {"disabled": 0},
	},
	"projects": {
		"doctype": "Project",
		"search_field": "project_name",
		"prompt_id": "projects_detail",
		"param_key": "project",
		"result_label": "Ver detalhe de {0}",
	},
}

# When a call includes one of these params, the answer is "about" that entity —
# the frontend uses this to enter a focused context (KPIs/comparisons scoped to
# it) until the user picks a different one or exits back to the section. Adding
# a new entity (supplier, project, ...) is just another entry here.
CONTEXT_PARAM_KEYS = {
	"customer": ("Customer", "customer_name"),
	"project": ("Project", "project_name"),
}


@frappe.whitelist()
def get_sections():
	return SECTIONS


@frappe.whitelist()
def search_entities(section_id, query):
	config = SEARCH_CONFIG.get(section_id)
	query = (query or "").strip()
	if not config or len(query) < 2:
		return []

	frappe.has_permission(config["doctype"], "read", throw=True)

	field = config["search_field"]
	filters = dict(config.get("extra_filters") or {})
	filters[field] = ["like", "%{0}%".format(query)]

	rows = frappe.get_list(
		config["doctype"],
		filters=filters,
		fields=["name", field],
		limit=20,
	)

	query_lower = query.lower()
	rows.sort(key=lambda r: (not (r.get(field) or "").lower().startswith(query_lower), (r.get(field) or "").lower()))

	results = []
	for r in rows[:8]:
		label_value = r.get(field) or r.name
		results.append({
			"id": config["prompt_id"],
			"label": config["result_label"].format(label_value),
			"display": label_value,
			"params": {config["param_key"]: r.name},
		})
	return results


@frappe.whitelist()
def ask(prompt_id, params=None):
	entry = HANDLERS.get(prompt_id)
	if not entry:
		frappe.throw(_("Pergunta desconhecida: {0}").format(prompt_id))

	handler, permission_doctype = entry
	frappe.has_permission(permission_doctype, "read", throw=True)

	params = frappe.parse_json(params) if isinstance(params, str) else (params or {})

	result = handler(**params) or {}
	result.setdefault("blocks", [])
	result.setdefault("follow_ups", [])
	result["prompt_label"] = PROMPT_LABELS.get(prompt_id) or result.get("title")

	for param_key, (doctype, label_field) in CONTEXT_PARAM_KEYS.items():
		if params.get(param_key):
			entity_id = params[param_key]
			label = frappe.db.get_value(doctype, entity_id, label_field) or entity_id
			result["context"] = {"type": param_key, "id": entity_id, "label": label}
			break

	return result
