from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ClinicForm,
    MachineForm,
    ReturnToServiceReportForm,
)
from .models import Department, Machine, ReturnToServiceReport
from .pdf import build_report_pdf


@login_required
def report_list(request):
    qs = ReturnToServiceReport.objects.select_related(
        "machine", "machine__department"
    )
    query = request.GET.get("q", "").strip()
    dept = request.GET.get("department", "").strip()
    status = request.GET.get("status", "").strip()

    if query:
        qs = qs.filter(
            Q(machine__name__icontains=query)
            | Q(work_performed__icontains=query)
            | Q(approved_by__icontains=query)
            | Q(performed_by__icontains=query)
        )
    if dept:
        qs = qs.filter(machine__department_id=dept)
    if status:
        qs = qs.filter(status=status)

    context = {
        "reports": qs,
        "departments": Department.objects.all(),
        "status_choices": ReturnToServiceReport.Status.choices,
        "q": query,
        "selected_department": dept,
        "selected_status": status,
        "total": ReturnToServiceReport.objects.count(),
    }
    return render(request, "reports/report_list.html", context)


@login_required
def report_detail(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related(
            "machine", "machine__department", "created_by"
        ),
        pk=pk,
    )
    return render(request, "reports/report_detail.html", {"report": report})


@login_required
def report_create(request):
    if request.method == "POST":
        form = ReturnToServiceReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.created_by = request.user
            report.save()
            return redirect(report)
    else:
        form = ReturnToServiceReportForm()
    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "title": "New return-to-service report",
            "has_machines": Machine.objects.exists(),
            "has_clinics": Department.objects.exists(),
        },
    )


@login_required
def report_edit(request, pk):
    report = get_object_or_404(ReturnToServiceReport, pk=pk)
    if request.method == "POST":
        form = ReturnToServiceReportForm(request.POST, instance=report)
        if form.is_valid():
            form.save()
            return redirect(report)
    else:
        form = ReturnToServiceReportForm(instance=report)
    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "title": f"Edit {report.reference}",
            "report": report,
            "has_machines": True,
            "has_clinics": True,
        },
    )


@login_required
def report_pdf(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related(
            "machine", "machine__department", "created_by"
        ),
        pk=pk,
    )
    buffer = build_report_pdf(report)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{report.reference}.pdf"'
    return response


# --- Clinic & machine management (selection options) ---

@login_required
def manage(request):
    clinics = (
        Department.objects.annotate(machine_count=Count("machines"))
        .prefetch_related("machines")
        .all()
    )
    return render(
        request,
        "reports/manage.html",
        {
            "clinics": clinics,
            "clinic_form": ClinicForm(),
            "machine_form": MachineForm(),
            "has_clinics": clinics.exists(),
        },
    )


@login_required
def clinic_create(request):
    if request.method == "POST":
        form = ClinicForm(request.POST)
        if form.is_valid():
            clinic = form.save()
            messages.success(request, f"Clinic “{clinic.name}” added.")
            return redirect("reports:manage")
        # Re-render manage page with errors in the clinic form.
        return render(
            request,
            "reports/manage.html",
            {
                "clinics": Department.objects.annotate(
                    machine_count=Count("machines")
                ).prefetch_related("machines"),
                "clinic_form": form,
                "machine_form": MachineForm(),
                "open_form": "clinic",
                "has_clinics": Department.objects.exists(),
            },
        )
    return redirect("reports:manage")


@login_required
def machine_create(request):
    if request.method == "POST":
        form = MachineForm(request.POST)
        if form.is_valid():
            machine = form.save()
            messages.success(
                request, f"Machine “{machine.name}” added to {machine.department.name}."
            )
            return redirect("reports:manage")
        return render(
            request,
            "reports/manage.html",
            {
                "clinics": Department.objects.annotate(
                    machine_count=Count("machines")
                ).prefetch_related("machines"),
                "clinic_form": ClinicForm(),
                "machine_form": form,
                "open_form": "machine",
                "has_clinics": Department.objects.exists(),
            },
        )
    return redirect("reports:manage")


@login_required
def machines_for_clinic(request):
    """JSON: machines belonging to a clinic, for the dependent dropdown."""
    clinic_id = request.GET.get("clinic")
    machines = []
    if clinic_id:
        machines = list(
            Machine.objects.filter(department_id=clinic_id)
            .order_by("name")
            .values("id", "name")
        )
    return JsonResponse({"machines": machines})
