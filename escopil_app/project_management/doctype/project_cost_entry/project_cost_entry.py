from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document


class ProjectCostEntry(Document):
	def validate(self):
		if self.is_new() or frappe.flags.in_project_cost_sync:
			return

		if not self.is_auto_generated:
			return

		before_save = self.get_doc_before_save()
		if not before_save:
			return

		protected_fields = (
			"project",
			"rubrica",
			"posting_date",
			"amount",
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
		if self.is_auto_generated and not frappe.flags.in_project_cost_sync:
			frappe.throw(
				_(
					"Não é possível eliminar um lançamento gerado automaticamente. "
					"Cancele o documento de origem ({0} {1}) em vez disso."
				).format(self.reference_doctype, self.reference_name)
			)
