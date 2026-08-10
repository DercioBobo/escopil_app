from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import (
	add_months,
	date_diff,
	flt,
	fmt_money,
	formatdate,
	get_first_day,
	get_last_day,
	getdate,
	nowdate,
)

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

	follow_ups = [{"id": "invoicing_overdue_invoices", "label": "Mostrar apenas faturas vencidas"}]
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
			},
		],
		"follow_ups": follow_ups,
	}


def h_overdue_invoices(**kwargs):
	rows = frappe.db.sql(
		"""
		select name, customer_name as customer, outstanding_amount as amount, due_date
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and due_date < %(today)s
		order by due_date asc
		limit 20
		""",
		{"today": nowdate()},
		as_dict=True,
	)

	if not rows:
		return {
			"title": "Faturas vencidas",
			"blocks": [{"type": "text", "text": "Não há faturas vencidas neste momento."}],
			"follow_ups": [{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"}],
		}

	today = getdate(nowdate())
	return {
		"title": "Faturas vencidas",
		"blocks": [{
			"type": "table",
			"columns": ["Fatura", "Cliente", "Valor", "Dias em Atraso"],
			"rows": [
				[r.name, r.customer, _money(r.amount), date_diff(today, r.due_date)]
				for r in rows
			],
		}],
		"follow_ups": [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_total_this_month", "label": "Quanto faturámos este mês?"},
		],
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
		}],
		"follow_ups": [
			{"id": "invoicing_top_debtors", "label": "Quais clientes nos devem mais?"},
			{"id": "invoicing_overdue_invoices", "label": "Quais faturas estão vencidas?"},
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
		],
	},
]

HANDLERS = {
	"invoicing_total_this_month": (h_total_this_month, "Sales Invoice"),
	"invoicing_total_vs_last_month": (h_total_vs_last_month, "Sales Invoice"),
	"invoicing_top_debtors": (h_top_debtors, "Sales Invoice"),
	"invoicing_overdue_invoices": (h_overdue_invoices, "Sales Invoice"),
	"invoicing_customer_detail": (h_customer_detail, "Sales Invoice"),
}

PROMPT_LABELS = {p["id"]: p["label"] for section in SECTIONS for p in section["prompts"]}


@frappe.whitelist()
def get_sections():
	return SECTIONS


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
