"""adiciona quantidade em itens_lista_compra

Revision ID: e67d4d0e9bdf
Revises: 0cc484b7b642
Create Date: 2026-07-16 00:17:29.912469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e67d4d0e9bdf'
down_revision: Union[str, None] = '0cc484b7b642'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Itens já sinalizados na lista antes de existir esse campo não tinham
    # conceito de quantidade — assume 1 unidade pra todos (ver decisão do
    # usuário e CLAUDE.md "Compatibilidade com dados existentes").
    with op.batch_alter_table('itens_lista_compra', schema=None) as batch_op:
        batch_op.add_column(sa.Column('quantidade', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('itens_lista_compra', schema=None) as batch_op:
        batch_op.drop_column('quantidade')
