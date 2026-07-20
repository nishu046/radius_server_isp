from django.db import models

# Create your models here.
# Packages Model

class Package(models.Model):
 name = models.CharField(max_length=245)
 speed = models.IntegerField()
 price = models.FloatField()

 class Meta:
  ordering = ['speed', 'name', 'id']

 def __str__(self):
  return self.name
