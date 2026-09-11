from django.contrib.auth import get_user_model
from datetime import timedelta
from decimal import Decimal
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from .models import Order, Product, MarketplaceEvent

@staff_member_required(login_url="login")
def analytics_dashboard(request):
    period=request.GET.get("period","30")
    if period not in {"7","30","90","all"}: period="30"
    start=timezone.now()-timedelta(days=int(period)) if period!="all" else None
    orders=Order.objects.filter(is_deleted=False)
    events=MarketplaceEvent.objects.all()
    if start:
        orders=orders.filter(created_at__gte=start)
        events=events.filter(created_at__gte=start)
    money=lambda qs,field: qs.aggregate(value=Sum(field))["value"] or Decimal("0")
    active=orders.exclude(status="cancelled")
    statuses=list(orders.values("status").annotate(count=Count("id"),value=Sum("total_price")).order_by("status"))
    labels=dict(Order._meta.get_field("status").choices)
    for row in statuses:row["label"]=labels.get(row["status"],row["status"])
    daily_orders={x["day"]:x for x in orders.annotate(day=TruncDate("created_at")).values("day").annotate(orders=Count("id"),value=Sum("total_price"))}
    daily_visits={x["day"]:x["count"] for x in events.filter(event_type="product_view").annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))}
    daily=[{"day":day,"orders":daily_orders.get(day,{}).get("orders",0),"value":daily_orders.get(day,{}).get("value",0),"visits":daily_visits.get(day,0)} for day in sorted(set(daily_orders)|set(daily_visits),reverse=True)][:90]
    context={"period":period,"order_count":orders.count(),"order_value":money(active,"total_price"),"deposits":money(orders.filter(deposit_confirmed=True),"deposit_amount"),"balances":money(orders.filter(balance_paid=True),"balance_amount"),"refunds":money(orders.filter(refund_status="completed"),"refund_amount"),"refunds_due":money(orders.filter(refund_status="due"),"refund_amount"),"unpaid_balances":money(active.filter(balance_paid=False),"balance_amount"),"pending_deposits":active.filter(deposit_confirmed=False).count(),"visits":events.filter(event_type="product_view").count(),"statuses":statuses,"daily":daily,"recent":orders.order_by("-created_at")[:50],"events":events.values("event_type").annotate(count=Count("id")).order_by("-count"),"top_products":events.filter(event_type="product_view",product__isnull=False).values("product__name").annotate(count=Count("id")).order_by("-count")[:10],"products":Product.objects.filter(is_deleted=False).count(),"visible_products":Product.objects.filter(is_deleted=False,status="active",is_available=True,show_on_homepage=True).count()}
    users=get_user_model().objects.all()
    new_users=users.filter(date_joined__gte=start) if start else users
    context.update({"registered_users":users.count(),"active_users":users.filter(is_active=True).count(),"new_users":new_users.count(),"page_views":events.filter(event_type="page_view").count(),"activity":events.filter(event_type__in=["page_view","product_view"]).select_related("user","product").order_by("-created_at")[:100],"user_activity":events.filter(user__isnull=False,event_type__in=["page_view","product_view"]).values("user__username").annotate(views=Count("id")).order_by("-views")[:50],"pages":events.filter(event_type="page_view").values("path").annotate(views=Count("id")).order_by("-views")[:30],"latest_users":new_users.order_by("-date_joined")[:30]})
    response=render(request,"core/analytics_dashboard.html",context)
    response["Cache-Control"]="private, no-store"
    return response
