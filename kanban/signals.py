"""Limpeza de blobs no object storage quando o registro é excluído.

O ORM do Django, ao apagar uma linha, NÃO remove o arquivo associado do
storage (S3/Railway Object Storage). Sem isto, todo documento excluído — e
todo anexo apagado em cascata quando uma pasta/projeto some — deixa um
arquivo órfão que continua ocupando espaço e gerando custo para sempre.

O post_delete dispara por instância, inclusive nas exclusões em cascata,
então cobre tanto a exclusão direta quanto a remoção da pasta/projeto pai.
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import PastaDocumento, CardAnexo, SubTaskAnexo


@receiver(post_delete, sender=PastaDocumento)
@receiver(post_delete, sender=CardAnexo)
@receiver(post_delete, sender=SubTaskAnexo)
def apagar_blob_ao_excluir(sender, instance, **kwargs):
    arquivo = instance.arquivo
    if arquivo:
        # save=False: não regravar a linha (que já está sendo apagada).
        arquivo.delete(save=False)
