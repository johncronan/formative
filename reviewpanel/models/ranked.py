from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.db.models import Max, Q, F, Case, When, Subquery, \
    ExpressionWrapper, IntegerField


class RankedModel(models.Model):
    class Meta:
        abstract = True
    
    rank = models.PositiveIntegerField(null=True)
    negrank = models.IntegerField(null=True)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self._initial_rank = self.rank

    def save(self, *args, **kwargs):
        if not self.pk or self.rank is None:
            with transaction.atomic():
                # newly created instance: it goes at the end
                if self.rank is not None:
                    raise ValidationError('New RankedModel instance already'
                                          'ranked - this is not supported')
                had_pk = self.pk
                # insert with NULL - in combination with atomic, acquires a lock
                obj = super().save(*args, **kwargs)
                if had_pk: return
                
                group = self.rank_group()
                query = group.aggregate(max_rank=Max('rank'))
                if query['max_rank'] is not None:
                    self.rank = query['max_rank'] + 1
                    self.negrank = -self.rank
                else: self.rank = self.negrank = 0
            
                super().save(*args, **kwargs)
                self._initial_rank = self.rank
                return
        
        n, positive = self.rank - self._initial_rank, True
        if n < 0: n, positive = -n, False
        elif not n:
            super().save(*args, **kwargs)
            return
        
        group = self.rank_group()
        
        # start from where we _really_ are, not where they think we are;
        # otherwise we're not actually locking the correct rows
        pos = Subquery(group.filter(pk=self.pk).values('rank')[:1])
        if positive:
            section = group.annotate(pos=pos).filter(rank__gte=F('pos'),
                                                     rank__lte=F('pos')+n)
        else:
            section = group.annotate(pos=pos).filter(rank__lte=F('pos'),
                                                     rank__gte=F('pos')-n)
        order = positive and 'rank' or '-rank'

        with transaction.atomic():
            query = section.order_by(order).select_for_update()
            for count, last_ranked in enumerate(query): pass # rows are locked
            new_rank = last_ranked.rank # we could have hit the end early
            
            self.rank = (not count) and new_rank or None
            if self.rank is not None: self.negrank = -self.rank
            else: self.negrank = None
            super().save(*args, **kwargs)
            
            self._initial_rank = self.rank
            if not count: return # we informed them of their misapprehension
            
            if positive: # self moving + direction means that the others move -
                section = group.filter(rank__gte=new_rank-count,
                                       rank__lte=new_rank)
                section.update(rank=F('rank') - 1, negrank=F('negrank') + 1)
            else:
                # they move out of the way in the other direction, but also, we
                # have to do the updates in the opposite order (hence negrank)
                section = group.filter(negrank__gte=-new_rank-count,
                                       negrank__lte=-new_rank)
                section.update(negrank=F('negrank') - 1, rank=F('rank') + 1)
            
            self.rank = new_rank
            self.negrank = -self.rank
            super().save(*args, **kwargs)
            self._initial_rank = self.rank
    
    @transaction.atomic
    def delete(self, *args, **kwargs):
        rank = self.rank
        self.rank = self.negrank = None
        if rank:
            self.save(update_fields=['rank', 'negrank']) # get the same lock
            section = self.rank_group().filter(rank__gt=rank)
            section.update(rank=F('rank')-1, negrank=F('negrank')+1)
        
        super().delete(*args, **kwargs)
    
    def rank_group(self):
        return self.__class__.objects.all()
