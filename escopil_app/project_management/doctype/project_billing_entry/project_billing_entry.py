from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_first_day


class ProjectBillingEntry(Document):
	def validate(self):
		self.month = get_first_day(self.month)

		duplicate = frappe.db.exists(
			"Project Billing Entry",
			{
				"project": self.project,
				"month": self.month,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Já existe um lançamento de faturação para o Projeto {0} no mês {1}.").format(
					self.project, self.month
				)
			)
