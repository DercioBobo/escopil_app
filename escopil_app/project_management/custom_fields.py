from __future__ import unicode_literals

custom_fields = {
	"Project": [
		dict(
			fieldname="custom_budget_rubricas",
			label="Rubricas do Orçamento",
			fieldtype="Table",
			options="Project Budget Rubrica",
			insert_after="cost_center",
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
