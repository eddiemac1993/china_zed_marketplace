from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

def seed(apps, schema_editor):
    Room = apps.get_model("communinity", "Room")
    for code, title, description in [("DEALS","Hot Deals Zambia","Discuss bargains and affordable finds."),("PHONE","Phones & Electronics","Phones, accessories and buying advice."),("STYLE","Fashion & Beauty","Clothing, shoes, hair and beauty."),("SOLAR","Solar & Backup Power","Solar lights, inverters and backup solutions."),("BIZZM","Business Opportunities","Equipment, starter packs and resale ideas."),("FINDI","Help Me Find This","Request products ChinaZed should source next.")]:
        Room.objects.update_or_create(code=code, defaults={"title":title,"description":description,"room_type":"public","is_active":True})

class Migration(migrations.Migration):
    dependencies = [("communinity", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="room",name="title",field=models.CharField(blank=True,max_length=100)),
        migrations.AddField(model_name="room",name="description",field=models.CharField(blank=True,max_length=240)),
        migrations.AddField(model_name="room",name="room_type",field=models.CharField(choices=[("private","Private anonymous room"),("public","Public community room")],default="private",max_length=10)),
        migrations.AddField(model_name="message",name="user",field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="community_messages",to=settings.AUTH_USER_MODEL)),
        migrations.CreateModel(name="MessageReaction",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("reaction_type",models.CharField(choices=[("helpful","Helpful"),("interested","I want this")],max_length=12)),("created_at",models.DateTimeField(auto_now_add=True)),("message",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="reactions",to="communinity.message")),("user",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="community_reactions",to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name="MessageReport",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("reason",models.CharField(blank=True,max_length=240)),("created_at",models.DateTimeField(auto_now_add=True)),("resolved",models.BooleanField(default=False)),("message",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="reports",to="communinity.message")),("user",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="community_reports",to=settings.AUTH_USER_MODEL))]),
        migrations.AddConstraint(model_name="messagereaction",constraint=models.UniqueConstraint(fields=("message","user","reaction_type"),name="unique_message_user_reaction")),
        migrations.AddConstraint(model_name="messagereport",constraint=models.UniqueConstraint(fields=("message","user"),name="unique_message_user_report")),
        migrations.RunPython(seed,migrations.RunPython.noop),
    ]
