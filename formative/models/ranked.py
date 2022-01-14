from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.db.models import Max, Q, F, Case, When, Subquery, \
    ExpressionWrapper, IntegerField


class UnderscoredRankedModel(models.Model):
    class Meta:
        abstract = True
    
    _rank = models.IntegerField(default=0)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self._initial_rank = None
        if '_rank' not in self.get_deferred_fields():
            self._initial_rank = self._rank

    def save(self, *args, **kwargs):
        if not self.pk or not self._rank: # self._rank == 0 for pass-thru
            with transaction.atomic():
                # newly created instance: it goes at the end
                if self._rank:
                    raise ValidationError('New RankedModel instance already'
                                          'ranked - this is not supported')
                had_pk = self.pk # remember that we're just passing thru
                # insert with zero - in combination with atomic, acquires a lock
                obj = super().save(*args, **kwargs)
                if had_pk: return
                
                group = self._rank_group()
                query = group.aggregate(max_rank=Max('_rank'))
                if query['max_rank'] is not None:
                    self._rank = query['max_rank'] + 1
                else: self._rank = 1
            
                super().save(*args, **kwargs)
                self._initial_rank = self._rank
                return
        
        n, positive = self._rank - self._initial_rank, True
        if n < 0: n, positive = -n, False
        elif not n:
            super().save(*args, **kwargs)
            return
        
        group = self._rank_group()
        
        # start from where we _really_ are, not where we thought we were;
        # otherwise we're not actually locking the correct rows
        pos = Subquery(group.filter(pk=self.pk).values('_rank')[:1])
        if positive:
            section = group.annotate(pos=pos).filter(_rank__gte=F('pos'),
                                                     _rank__lte=F('pos')+n)
        else:
            section = group.annotate(pos=pos).filter(_rank__lte=F('pos'),
                                                     _rank__gte=F('pos')-n)

        with transaction.atomic():
            order = positive and '_rank' or '-_rank'
            query = section.order_by(order).select_for_update()
            for count, last_ranked in enumerate(query): pass # rows are locked
            new_rank = last_ranked._rank # we could have hit the end early
            
            if not count:
                # nothing to do; we just had a misapprehension
                self._rank = new_rank
                super().save(*args, **kwargs)
                self._initial_rank = self._rank
                return
            
            if positive: # this moving + direction means that the others move -
                section = group.filter(_rank__gt=new_rank-count,
                                       _rank__lte=new_rank)
                # use the negatives as a temporary space, to avoid key conflicts
                section.update(_rank=-F('_rank'))
                increment = -1
                section = group.filter(_rank__gte=-new_rank,
                                       _rank__lt=-new_rank+count)
            else:
                # they move out of the way in the other direction
                section = group.filter(_rank__gte=new_rank,
                                       _rank__lt=new_rank+count)
                section.update(_rank=-F('_rank'))
                increment = 1
                section = group.filter(_rank__gt=-new_rank-count,
                                       _rank__lte=-new_rank)
            
            self._rank = new_rank
            super().save(*args, **kwargs)
            self._initial_rank = self._rank
            
            # make the others positive again, with the increment applied
            section.update(_rank=-F('_rank')+increment)
    
    @transaction.atomic
    def delete(self, *args, **kwargs):
        rank = self._rank
        self._rank = 0
        if rank:
            self.save(update_fields=['_rank']) # get the same lock
            group = self._rank_group()
            group.filter(_rank__gt=rank).update(_rank=-F('_rank'))
            group.filter(_rank__lt=-rank).update(_rank=-F('_rank')-1)
        
        super().delete(*args, **kwargs)
    
    def _rank_group(self):
        if hasattr(self, 'rank_group') and callable(self.rank_group):
            return self.rank_group()
        
        return self.__class__.objects.all()


class RankedModel(UnderscoredRankedModel):
    class Meta:
        abstract = True
    
    @property
    def rank(self):
        return self._rank
    
    @rank.setter
    def rank(self, value):
        self._rank = value
    
    def rank_group(self):
        return self.__class__.objects.all()