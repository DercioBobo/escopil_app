from __future__ import unicode_literals

custom_fields = {
	"Project": [
		dict(
			fieldname="custom_cost_control_section",
			label="Controlo de Custos e Faturação",
			fieldtype="Section Break",
			insert_after="cost_center",
		),
		dict(
			fieldname="custom_cost_control_enabled",
			label="Ativar Controlo de Custos e Faturação",
			fieldtype="Check",
			insert_after="custom_cost_control_section",
			description="Ativa o Painel de Orçamento e as secções de Custos/Faturação para este projeto.",
		),
		dict(
			fieldname="custom_monthly_billing_forecast",
			label="Previsão Mensal de Faturação (Padrão)",
			fieldtype="Currency",
			insert_after="custom_cost_control_enabled",
			depends_on="eval:doc.custom_cost_control_enabled",
			description="Valor de referência aplicado a todos os meses; pode ser ajustado por mês abaixo.",
		),
		dict(
			fieldname="custom_billing_forecast_overrides",
			label="Previsão de Faturação (Ajustes Mensais)",
			fieldtype="Table",
			options="Project Billing Forecast",
			insert_after="custom_monthly_billing_forecast",
			depends_on="eval:doc.custom_cost_control_enabled",
		),
		dict(
			fieldname="custom_budget_rubricas",
			label="Rubricas do Orçamento",
			fieldtype="Table",
			options="Project Budget Rubrica",
			insert_after="custom_billing_forecast_overrides",
			depends_on="eval:doc.custom_cost_control_enabled",
		),
	],
	"Material Request": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica (Padrão)",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
			description="Aplica esta rubrica a todos os itens abaixo.",
		),
	],
	"Purchase Order": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica (Padrão)",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
			description="Aplica esta rubrica a todos os itens abaixo.",
		),
	],
	"Purchase Invoice": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica (Padrão)",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
			description="Aplica esta rubrica a todos os itens abaixo.",
		),
	],
	"Material Request Item": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
		),
	],
	"Purchase Order Item": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
		),
	],
	"Purchase Invoice Item": [
		dict(
			fieldname="custom_rubrica",
			label="Rubrica",
			fieldtype="Link",
			options="Project Rubrica",
			insert_after="project",
		),
	],
}
