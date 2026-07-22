from __future__ import unicode_literals

custom_fields = {
	"Project": [
		dict(
			fieldname="custom_cost_control_enabled",
			label="Controlo de Custos e Faturação",
			fieldtype="Check",
			insert_after="cost_center",
			description="Ativa o Painel de Orçamento e as secções de Custos/Faturação para este projeto.",
		),
		dict(
			fieldname="custom_budget_rubricas",
			label="Rubricas do Orçamento",
			fieldtype="Table",
			options="Project Budget Rubrica",
			insert_after="custom_cost_control_enabled",
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
