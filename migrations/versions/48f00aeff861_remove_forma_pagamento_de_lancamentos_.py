"""remove forma_pagamento de lancamentos_fatura

Revision ID: 48f00aeff861
Revises: e67d4d0e9bdf
Create Date: 2026-07-16 00:47:54.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48f00aeff861'
down_revision: Union[str, None] = 'e67d4d0e9bdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # App passa a assumir que todo gasto é cartão de crédito — a distinção
    # crédito/refeição deixou de existir (decisão do usuário). Nenhum dado
    # histórico é perdido em termos de valor/data/categoria, só a coluna
    # que guardava essa classificação, que não é mais consultada em lugar
    # nenhum do app.
    with op.batch_alter_table('lancamentos_fatura', schema=None) as batch_op:
        batch_op.drop_column('forma_pagamento')


def downgrade() -> None:
    with op.batch_alter_table('lancamentos_fatura', schema=None) as batch_op:
        batch_op.add_column(sa.Column('forma_pagamento', sa.String(length=8), nullable=False, server_default='credito'))
