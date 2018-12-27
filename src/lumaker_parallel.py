#-*- using:utf-8 -*-
import collections
import threading
import logging
import os
import pickle
import queue
import sys
import time

import fiona
from shapely import geometry, ops
# import numpy as np

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# グローバル変数

# base_dir = "C:/ICP/qgis/projects/"
base_dir = "C:/qgis/ICP/qgis/projects/"
# base_dir = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/"

new_link_file = "minato-ku/minato-link-new.shp"
# new_link_file = "ohta-ku/road_link_ohta-ku_new.shp"
# new_link_file = "tokyo/road_link_tokyo_new.shp"
# new_link_file = "mapfan/link_new.shp"

link_file = "minato-ku/minato-link.shp"
# link_file = "tokyo/road_link_tokyo.shp"
# link_file = "ohta-ku/road_link_ohta-ku.shp"
# link_file = "mapfan/link_merged.shp"

node_file = "minato-ku/minato-node-new.shp"
# node_file = "tokyo/road_node_tokyo_new.shp"
# node_file = "ohta-ku/road_node_ohta-ku_new.shp"
# node_file = "mapfan/merged_node_new.shp"

new_link_path = base_dir + new_link_file
link_path = base_dir + link_file
node_path = base_dir + node_file

# cache dir
PICKLE_FILE_DIR = base_dir + "cache/"

# new objectid 30,000,000からスタート
new_id = 30000000

QUEUE_SIZE = 3000
lock = threading.Lock()
sentinel = object() # キューの最後を表すオブジェクト
meta = dict()
inq = queue.Queue(maxsize=QUEUE_SIZE)
outq = queue.Queue(maxsize=QUEUE_SIZE)

from_node_links = {}
to_node_links = {}
# newlinks = collections.deque()
cross_nodes = collections.deque()
all_nodes = collections.deque()
merged_link_count = 0
all_link_count = 0



# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count',
                   'ts_drm_tri', 'legal_spee', 'legal_sp_1')


# 属性の値が同一かチェック
def check_attributes(f, t):
    global checkAttributes
    if f is None or t is None:
        return False

    for attr in checkAttributes:
        if f['properties'][attr] != t['properties'][attr]:
            return False
        else:
            return True


# リンクを逆向きに
def reverse_link(link):
    # 一方通行種別 正方向1,3 <=> 逆方向2,4
    if link['properties']['oneway_c'] == 1:
        link['properties']['oneway_c'] = 3
    elif link['properties']['oneway_c'] == 3:
        link['properties']['oneway_c'] = 1
    elif link['properties']['oneway_c'] == 2:
        link['properties']['oneway_c'] = 4
    elif link['properties']['oneway_c'] == 4:
        link['properties']['oneway_c'] = 2

    # リンク方向コード 1:正方向 2:逆方向
    if link['properties']['linkdir_c'] == 1:
        link['properties']['linkdir_c'] = 2
    elif link['properties']['linkdir_c'] == 2:
        link['properties']['linkdir_c'] = 1

    # coordinates listを逆順に
    link['properties']['coordinates'] = link['properties']['coordinates'][::-1]

    return link


# def flatten(nested_list):
#     # フラットなリストとフリンジを用意
#     flat_list = []
#     fringe = [nested_list]
#     while len(fringe) > 0:
#         node = fringe.pop(0)
#         # ノードがリストであれば子要素をフリンジに追加
#         # リストでなければそのままフラットリストに追加
#         if isinstance(node, list):
#             fringe = node + fringe
#         else:
#             flat_list.append(node)
#
#     return flat_list


# ジオメトリLineStringを結合し、MultiLineStringにする
def merge_linestrings(first, second):

    new_coordinates = []

    first_geometry = first['geometry']
    second_geometry = second['geometry']

    f_lines = []
    if first_geometry['type'] == 'MultiLineString':
        first = geometry.MultiLineString(first_geometry['coordinates'])
        for f in first:
            f_lines.append(f)
    else:
        f_lines.append(geometry.LineString(first_geometry['coordinates']))

    if second_geometry['type'] == 'MultiLineString':
        second = geometry.MultiLineString(second_geometry['coordinates'])
        for s in second:
            f_lines.append(s)
    else:
        f_lines.append(geometry.LineString(second_geometry['coordinates']))

    merged_multiline = geometry.MultiLineString(f_lines)
    linestring = ops.linemerge(merged_multiline)
    return linestring


# リンクを接合
def merge_links(a, b, node):

    # 新しいobjectid
    global new_id
    multi = False

    # ノードの位置を特定
    aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    aNodePos = aNodes.index(node)
    bNodePos = bNodes.index(node)

    # coordinates
    newc = []

    # 両リンクの向きを確認 同一方向に
    # <-a- n -b->  =>  -a-> n -b->
    if aNodePos == 0 and bNodePos == 0:
        a = reverse_link(a)
        bc.reverse()
        # shape
        newc = merge_linestrings(b, a)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # -a-> n -b->  or <-b- n <-a- =>  keep
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc = merge_linestrings(a, b)
    # <-a- n <-b- => or -b-> n -a-> keep
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc = merge_linestrings(b, a)
    # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc = merge_linestrings(a, b)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]
    new_id = new_id + 1
    a['properties']['objectid'] = new_id
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['tonodeid'] = newtonodeid
    a['geometry'] = geometry.mapping(newc)
    if multi:
        a['geometry']['type'] = "MultiLineString"
    return a


def get_link(node, from_node_links, to_node_links):
    # 接合対象のリンクを特定し、辞書から削除
    if node in from_node_links.keys():
        f = from_node_links.pop(node)
        # print(f"fromlink:{fromlink}")
        if node in to_node_links.keys():
            t = to_node_links.pop(node)
            return f, t
    return None, None


# def remove_link(f, t):
#     global newlinks
#     return [x for x in newlinks if not x in (f, t)]


def make_lu(node_id):
    global from_node_links, to_node_links, merged_link_count
    from_link, to_link = get_link(node_id, from_node_links, to_node_links)
    if check_attributes(from_link, to_link):
        # remove_link(from_link, to_link)
        new_link = merge_links(from_link, to_link, node_id)
        new_from_node_id = new_link['properties']['fromnodeid']
        new_to_node_id = new_link['properties']['tonodeid']
        from_node_links[new_from_node_id] = new_link
        to_node_links[new_to_node_id] = new_link
        # newlinks.append(new_link)
        if new_link['id'] == '7505':
            print('new')
        return new_link


def process(inqueue, outqueue):
    print('start process')
    for node in iter(inqueue.get, sentinel):
        if node['properties']['connlink'] == 2:
            node_id = node['properties']['objectid']
            result = make_lu(node_id)
            outqueue.put(result)
    outqueue.put(sentinel)


def write_file(path, q):
    print('start writing')
    global meta, lock, merged_link_count
    with fiona.open(path, 'w', **meta) as f:
        for line in iter(q.get, sentinel):
            if line is not None:
                # print(line)
                # with lock:
                merged_link_count = merged_link_count + 1
                # print(merged_link_count)
                # print(line)
                f.write(line)


def read_file(link_path, node_path, queue):
    global meta, all_link_count
    with fiona.open(link_path, "r") as fl:
        meta = fl.meta
        with fiona.open(node_path, "r") as fn:
            for v in fn:
                queue.put(v)
                # with lock:
                all_link_count = all_link_count + 1
        queue.put(sentinel)


# pickleにキャシュとして保存
def save_cache(path, cache):
    try:
        with open(path, 'wb') as f:
            print(f'  Saving pickle file ({path}.pickle)')
            pickle.dump(cache, f)
    except PermissionError as e:
        print(f'Permission Error. skipped {path}.pickle. {e} ')


# pickleから読み込み
def load_cache(path):
    with open(path, 'rb') as f:
        try:
            return pickle.load(f)
        except PermissionError as e:
            print(f'Permission Error when loading cache: {path} {e}')


def main():
    global link_path, node_path, new_link_path, inq, outq

    with fiona.open(link_path, "r") as fl:
        print('reading links')
        # pickle_path = os.path.join(PICKLE_FILE_DIR, link_file + ".pickle")
        # if os.path.exists(pickle_path):
        #     # キャッシュあれば読み込み
        #     print(f'Found pickle file ({os.path.basename(pickle_path)}). loading..')
        #     cross_nodes, from_node_links, to_node_links = load_cache(pickle_path)
        # else:
        for feature in fl:
            # all_nodes.append(feature['properties']['fromnodeid'])
            # all_nodes.append(feature['properties']['tonodeid'])
            from_node_id = feature['properties']['fromnodeid']
            from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            to_node_id = feature['properties']['tonodeid']
            to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            # all_link_count = all_link_count + 1

        # 2つのリンクが接続されているノードのobjectid属性を抽出
        # c = collections.Counter(all_nodes)
        # cross_nodes = [k for k, v in c.items() if v == 2]
        # save_cache(pickle_path, (cross_nodes, from_node_links, to_node_links))

    print('start threading')

    # read by single thread
    reader = threading.Thread(target=read_file, args=(link_path, node_path, inq))
    reader.start()

    # process by multiple threads
    threads = []
    for _ in range(1):
        thread = threading.Thread(target=process, args=(inq, outq))
        thread.start()
        threads.append(thread)
    # write  by single thread
    writer = threading.Thread(target=write_file, args=(new_link_path, outq))
    writer.start()

    # wait
    reader.join()
    print('reader end')
    for thread in threads:
        thread.join()
        print('process thread end')
    writer.join()
    print('writer end')

    print(f"Finished.  All Links counts: {all_link_count}, Generated LUs: {merged_link_count}")


if __name__ == '__main__':
    start = time.time()
    # リンクレイヤからfromnodeid, tonodeid を取得し、Dict[objectid] 形式で辞書化　
    main()
    elapsed_time = time.time() - start
    print("elapsed_time: {:.3f}".format(elapsed_time) + "[sec]")

