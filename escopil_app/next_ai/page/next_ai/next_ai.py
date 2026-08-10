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

OVERDUE_PAGE_SIZE = 20

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

	total = cint(frappe.db.sql(
		"""
		select count(*)
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		""",
		{"today": nowdate()},
	)[0][0])

	rows = frappe.db.sql(
		"""
		select name, customer, customer_name, outstanding_amount as amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		order by due_date asc
		limit %(limit)s offset %(offset)s
		""",
		{"today": nowdate(), "limit": OVERDUE_PAGE_SIZE, "offset": offset},
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
			"label": "Mostrar mais {0}".format(min(OVERDUE_PAGE_SIZE, remaining)),
			"params": {"offset": shown_upto},
			"remaining": remaining,
		}

	blocks = [
		{
			"type": "text",
			"text": "A mostrar {0} de {1} faturas vencidas, das mais antigas para as mais recentes.".format(
				shown_upto, total
			),
		},
		table_block,
	]

	follow_ups = [
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

	rows = frappe.db.sql(
		"""
		select name, posting_date, grand_total, outstanding_amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and customer = %(customer)s and outstanding_amount > 0
		order by due_date asc
		""",
		{"customer": customer},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Detalhe de {0}".format(customer_name),
			"blocks": [{"type": "text", "text": "{0} não tem faturas em aberto.".format(customer_name)}],
			"follow_ups": [{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"}],
		}

	today = getdate(nowdate())
	return {
		"title": "Faturas em aberto de {0}".format(customer_name),
		"blocks": [{
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
				for r in rows
			],
			"link_column": {"index": 0, "doctype": "Sales Invoice", "names": [r.name for r in rows]},
		}],
		"follow_ups": [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
		],
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
				],
			},
		],
		"follow_ups": [
			{"id": "invoicing_annual_comparison", "label": "Comparar com o ano passado"},
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
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


def _top_customers_response(rows, title, other_scope_follow_up):
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
		"follow_ups": [
			other_scope_follow_up,
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
		],
	}


def h_top_customers_year(**kwargs):
	year = getdate(nowdate()).year
	start = getdate("{0}-01-01".format(year))
	end = getdate(nowdate())
	rows = _top_customers(start, end)
	return _top_customers_response(
		rows,
		"Maiores clientes em {0}".format(year),
		{"id": "invoicing_top_customers_alltime", "label": "Ver desde sempre"},
	)


def h_top_customers_alltime(**kwargs):
	rows = _top_customers()
	return _top_customers_response(
		rows,
		"Maiores clientes (desde sempre)",
		{"id": "invoicing_top_customers_year", "label": "Ver apenas este ano"},
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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SECTIONS = [
	{
		"id": "invoicing",
		"label": "Faturação",
		"prompts": [
			{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
			{"id": "invoicing_total_vs_last_month", "label": "Quanto faturámos este mês vs mês passado?"},
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
			{"id": "invoicing_total_this_year", "label": "Quanto faturámos este ano?"},
			{"id": "invoicing_annual_comparison", "label": "Comparar faturação anual (este ano vs ano passado)"},
			{"id": "invoicing_top_customers_year", "label": "Quais são os maiores clientes este ano?"},
			{"id": "invoicing_top_customers_alltime", "label": "Quais são os maiores clientes de sempre?"},
			{"id": "invoicing_top_invoices_month", "label": "Quais as maiores faturas emitidas este mês?"},
		],
	},
]

HANDLERS = {
	"invoicing_total_this_month": (h_total_this_month, "Sales Invoice"),
	"invoicing_total_vs_last_month": (h_total_vs_last_month, "Sales Invoice"),
	"invoicing_top_debtors": (h_top_debtors, "Sales Invoice"),
	"invoicing_overdue_invoices": (h_overdue_invoices, "Sales Invoice"),
	"invoicing_customer_detail": (h_customer_detail, "Sales Invoice"),
	"invoicing_total_this_year": (h_total_this_year, "Sales Invoice"),
	"invoicing_annual_comparison": (h_annual_comparison, "Sales Invoice"),
	"invoicing_top_customers_year": (h_top_customers_year, "Sales Invoice"),
	"invoicing_top_customers_alltime": (h_top_customers_alltime, "Sales Invoice"),
	"invoicing_top_invoices_month": (h_top_invoices_month, "Sales Invoice"),
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
	return result
