-- 0) 직원 접속 토큰 (계정당 1개). v1 코드는 이 컬럼을 읽지 않으므로 v1 에 영향 없음.
alter table accounts add column if not exists staff_token text unique;

-- 1) 방송 세션
create table if not exists live_broadcasts (
  id              uuid primary key default gen_random_uuid(),
  owner_user_id   text not null,                    -- accounts.user_id (이메일)
  title           text not null,
  scheduled_at    timestamptz not null,
  memo            text,
  status          text not null default 'open'
                  check (status in ('open', 'closed')),
  last_order_seq  int  not null default 0,          -- 주문번호 순번 발급용
  created_at      timestamptz not null default now(),
  closed_at       timestamptz
);
create index if not exists live_broadcasts_owner_idx
  on live_broadcasts (owner_user_id, scheduled_at desc);

-- 2) 방송별 상품 카탈로그 (가격 포함)
create table if not exists live_products (
  id            uuid primary key default gen_random_uuid(),
  broadcast_id  uuid not null references live_broadcasts(id) on delete cascade,
  sort_order    int  not null,
  product_name  text not null,
  option_name   text not null default '단일상품',
  price         int  not null check (price >= 0),
  is_active     boolean not null default true,
  unique (broadcast_id, product_name, option_name)
);

-- 3) 주문 (고객 1명 = 1건)
create table if not exists live_orders (
  id              uuid primary key default gen_random_uuid(),
  broadcast_id    uuid not null references live_broadcasts(id),
  owner_user_id   text not null,                    -- 검색용 비정규화
  order_seq       int  not null,
  order_number    text not null,                    -- 'YYYYMMDD' || lpad(seq, 3, '0')
  staff_name      text not null,
  chat_name       text,
  customer_name   text not null,
  phone           text not null,                    -- 010-XXXX-XXXX 정규화 저장
  phone_digits    text not null,                    -- 숫자만. 검색용
  address          text not null,
  address_detail  text,
  search_address  text,                             -- 엑셀 추출 시 LLM 이 정제한 도로명주소 (재조회 캐시)
  zip_code        text,
  memo            text,
  status          text not null default 'received'
                  check (status in ('received', 'cancelled')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz,
  unique (broadcast_id, order_seq)
);
create index if not exists live_orders_owner_created_idx on live_orders (owner_user_id, created_at desc);
create index if not exists live_orders_phone_idx        on live_orders (owner_user_id, phone_digits);
create index if not exists live_orders_name_idx         on live_orders (owner_user_id, customer_name);
create index if not exists live_orders_broadcast_idx    on live_orders (broadcast_id, status);

-- 4) 주문 아이템 (상품 1행). 카탈로그가 바뀌어도 당시 값을 보존하도록 이름·단가 스냅샷
create table if not exists live_order_items (
  id            uuid primary key default gen_random_uuid(),
  order_id      uuid not null references live_orders(id) on delete cascade,
  product_id    uuid references live_products(id),
  product_name  text not null,
  option_name   text not null,
  unit_price    int  not null,
  quantity      int  not null check (quantity > 0)
);
create index if not exists live_order_items_order_idx on live_order_items (order_id);

-- 5) 방송별 주문 순번 원자 발급. 동시 저장 시 UPDATE 행 잠금으로 직렬화된다.
create or replace function live_next_order_seq(p_broadcast_id uuid)
returns int language sql as $$
  update live_broadcasts
     set last_order_seq = last_order_seq + 1
   where id = p_broadcast_id
  returning last_order_seq;
$$;
