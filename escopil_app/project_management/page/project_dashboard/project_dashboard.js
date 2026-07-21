frappe.pages['project-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Project Dashboard',
		single_column: true
	});

	frappe.project_dashboard = new ProjectDashboard(page);
};

class ProjectDashboard {
	constructor(page) {
		this.page = page;
		this.render();
	}

	render() {
		// TODO: replace with the Project Dashboard HTML
		$(this.page.body).html(`
			<div class="project-dashboard">
				<!-- Project Dashboard content goes here -->
			</div>
		`);
	}
}
