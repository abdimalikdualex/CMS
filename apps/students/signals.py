from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.services.finance_service import ensure_invoice_for_enrollment
from apps.students.models import Enrollment


@receiver(post_save, sender=Enrollment)
def enrollment_create_billing(sender, instance: Enrollment, created: bool, **kwargs):
    if created:
        ensure_invoice_for_enrollment(instance)
