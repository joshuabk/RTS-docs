from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from .forms import (
    ClinicForm,
    MachineForm,
    ReturnToServiceReportForm,
)
from .models import Department, Machine, ReturnToServiceReport
from .pdf import build_report_pdf
from .admin_gate import SESSION_KEY, check_credentials, manage_admin_required

from django.db.models.deletion import ProtectedError
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme



# rtsadmin,   northsiderts

def report_list(request):
    qs = ReturnToServiceReport.objects.select_related(
        "machine", "machine__department"
    )
    dept = request.GET.get("department", "").strip()
    machine_id = request.GET.get("machine", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    # Machine options follow the clinic filter; a machine from another
    # clinic (left over after the clinic changed) is ignored.
    machines = Machine.objects.select_related("department")
    if dept:
        qs = qs.filter(machine__department_id=dept)
        machines = machines.filter(department_id=dept)
    if machine_id and not machines.filter(pk=machine_id).exists():
        machine_id = ""
    if machine_id:
        qs = qs.filter(machine_id=machine_id)
    if status:
        qs = qs.filter(status=status)
    if date_from:
        parsed = parse_date(date_from)
        if parsed:
            qs = qs.filter(work_completed_at__date__gte=parsed)
        else:
            date_from = ""
    if date_to:
        parsed = parse_date(date_to)
        if parsed:
            qs = qs.filter(work_completed_at__date__lte=parsed)
        else:
            date_to = ""

    context = {
        "reports": qs,
        "departments": Department.objects.all(),
        "machines": machines,
        "status_choices": ReturnToServiceReport.Status.choices,
        "selected_department": dept,
        "selected_machine": machine_id,
        "selected_status": status,
        "date_from": date_from,
        "date_to": date_to,
        "total": ReturnToServiceReport.objects.count(),
    }
    return render(request, "reports/report_list.html", context)


def report_detail(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related(
            "machine", "machine__department", "created_by"
        ),
        pk=pk,
    )
    return render(request, "reports/report_detail.html", {"report": report})


def report_create(request):
    if request.method == "POST":
        form = ReturnToServiceReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.created_by = request.user if request.user.is_authenticated else None
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


def report_delete(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related("machine", "machine__department"),
        pk=pk,
    )
    if request.method == "POST":
        reference = report.reference
        report.delete()
        messages.success(request, f"Report {reference} deleted.")
        return redirect("reports:list")
    return render(
        request,
        "reports/confirm_delete.html",
        {
            "kind": "report",
            "object_name": f"{report.reference} — {report.machine.name}",
            "detail": report.machine.department.name,
            "eyebrow": "Return-to-service register",
            "back_url": report.get_absolute_url(),
            "back_label": f"← {report.reference}",
            "action_url": reverse("reports:delete", args=[report.pk]),
        },
    )


# --- Clinic & machine management (selection options) ---

def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return default


def manage_login(request):
    """Admin sign-in required before the clinic & machine pages."""
    error = ""
    if request.method == "POST":
        if check_credentials(
            request.POST.get("username", "").strip(), request.POST.get("password", "")
        ):
            request.session[SESSION_KEY] = True
            return redirect(_safe_next(request, reverse("reports:manage")))
        error = "Admin username and password didn't match. Please try again."
    return render(
        request,
        "registration/manage_login.html",
        {"error": error, "next": request.GET.get("next", "")},
    )


def manage_logout(request):
    if request.method == "POST":
        request.session.pop(SESSION_KEY, None)
        messages.success(request, "Signed out of admin.")
    return redirect("reports:list")


@manage_admin_required
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


@manage_admin_required
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

@manage_admin_required
def clinic_edit(request, pk):
    clinic = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        form = ClinicForm(request.POST, instance=clinic)
        if form.is_valid():
            form.save()
            messages.success(request, f"Clinic “{clinic.name}” updated.")
            return redirect("reports:manage")
    else:
        form = ClinicForm(instance=clinic)
    return render(
        request,
        "reports/object_form.html",
        {"form": form, "kind": "clinic", "title": f"Edit clinic — {clinic.name}"},
    )


@manage_admin_required
def clinic_delete(request, pk):
    clinic = get_object_or_404(Department, pk=pk)
    machine_count = clinic.machines.count()
    if request.method == "POST":
        if machine_count:
            messages.error(
                request,
                f"Can’t delete “{clinic.name}” — it still has {machine_count} "
                f"machine{'s' if machine_count != 1 else ''}. Delete or reassign them first.",
            )
            return redirect("reports:manage")
        name = clinic.name
        try:
            clinic.delete()
            messages.success(request, f"Clinic “{name}” deleted.")
        except ProtectedError:
            messages.error(request, f"Can’t delete “{name}” — other records depend on it.")
        return redirect("reports:manage")

    blocked_reason = ""
    if machine_count:
        blocked_reason = (
            f"This clinic still has {machine_count} "
            f"machine{'s' if machine_count != 1 else ''}. "
            "Delete or reassign its machines before removing the clinic."
        )
    return render(
        request,
        "reports/confirm_delete.html",
        {
            "kind": "clinic",
            "object_name": clinic.name,
            "detail": clinic.location,
            "blocked_reason": blocked_reason,
            "action_url": reverse("reports:clinic_delete", args=[clinic.pk]),
        },
    )




@manage_admin_required
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

@manage_admin_required
def machine_edit(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    if request.method == "POST":
        form = MachineForm(request.POST, instance=machine)
        if form.is_valid():
            form.save()
            messages.success(request, f"Machine “{machine.name}” updated.")
            return redirect("reports:manage")
    else:
        form = MachineForm(instance=machine)
    return render(
        request,
        "reports/object_form.html",
        {"form": form, "kind": "machine", "title": f"Edit machine — {machine.name}"},
    )


@manage_admin_required
def machine_delete(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    report_count = machine.rts_reports.count()
    if request.method == "POST":
        if report_count:
            messages.error(
                request,
                f"Can’t delete “{machine.name}” — it is used by {report_count} "
                f"report{'s' if report_count != 1 else ''}. Those records must be kept.",
            )
            return redirect("reports:manage")
        name = machine.name
        try:
            machine.delete()
            messages.success(request, f"Machine “{name}” deleted.")
        except ProtectedError:
            messages.error(request, f"Can’t delete “{name}” — other records depend on it.")
        return redirect("reports:manage")

    blocked_reason = ""
    if report_count:
        blocked_reason = (
            f"This machine is referenced by {report_count} "
            f"return-to-service report{'s' if report_count != 1 else ''}, "
            "which must be preserved. It can’t be deleted."
        )
    return render(
        request,
        "reports/confirm_delete.html",
        {
            "kind": "machine",
            "object_name": machine.name,
            "detail": machine.department.name,
            "blocked_reason": blocked_reason,
            "action_url": reverse("reports:machine_delete", args=[machine.pk]),
        },
    )


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
