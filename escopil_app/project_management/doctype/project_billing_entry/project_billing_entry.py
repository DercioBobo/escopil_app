from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_first_day


class ProjectBillingEntry(Document):
	def validate(self):
		self.month = get_first_day(self.month)

		if self.is_auto_generated:
			self._check_auto_generated_edit()
			return

		duplicate = frappe.db.exists(
			"Project Billing Entry",
			{
				"project": self.project,
				"month": self.month,
				"is_auto_generated": 0,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Já existe um lançamento manual de faturação para o Projeto {0} no mês {1}.").format(
					self.project, self.month
				)
			)

	def _check_auto_generated_edit(self):
		if self.is_new() or frappe.flags.in_project_billing_sync:
			return

		before_save = self.get_doc_before_save()
		if not before_save:
			return

		protected_fields = (
			"project",
			"month",
			"billable_amount",
			"reference_doctype",
			"reference_name",
			"is_auto_generated",
		)
		for fieldname in protected_fields:
			if before_save.get(fieldname) != self.get(fieldname):
				frappe.throw(
					_("Não é possível editar um lançamento gerado automaticamente a partir de {0} {1}.").format(
						self.reference_doctype, self.reference_name
					)
				)

	def on_trash(self):
		if self.is_auto_generated and not frappe.flags.in_project_billing_sync:
			frappe.throw(
				_(
					"Não é possível eliminar um lançamento gerado automaticamente. "
					"Cancele o documento de origem ({0} {1}) em vez disso."
				).format(self.reference_doctype, self.reference_name)
			)
