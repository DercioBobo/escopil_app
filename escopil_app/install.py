from __future__ import unicode_literals

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from escopil_app.project_management.custom_fields import custom_fields


def after_install():
	create_custom_fields(custom_fields, update=True)
