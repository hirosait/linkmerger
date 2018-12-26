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
from shapely.geometry import mapping, shape
# import numpy as np

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# グローバル変数

base_dir = "C:/ICP/qgis/projects/"
# base_dir = "C:/qgis/ICP/qgis/projects/"
# base_dir = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/"

new_link_file = "minato-ku/minato-link-new.shp"
# new_link_file = "/tokyo/road_link_tokyo_new.shp"
link_file = "minato-ku/minato-link.shp"
# link_file = "tokyo/road_link_tokyo.shp"
node_file = "minato-ku/minato-node.shp"
# node_file = "tokyo/road_node_tokyo.shp"

new_link_path = base_dir + new_link_file
link_path = base_dir + link_file
node_path = base_dir + node_file

# cache dir
PICKLE_FILE_DIR = base_dir + "cache/"

# new objectid 30,000,000からスタート
new_id = 30000000

QUEUE_SIZE = 1000

sentinel = object() # キューの最後を表すオブジェクト
meta = dict()
inq = queue.Queue(maxsize=QUEUE_SIZE)
outq = queue.Queue(maxsize=QUEUE_SIZE)



from_node_links = {}
to_node_links = {}
newlinks = collections.deque()
all_nodes = collections.deque()

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count',
                   'ts_drm_tri', 'legal_spee', 'legal_sp_1')

# 属性の値が同一かチェック
def check_attributes(f, t):
    global checkAttributes
    if f is None or t is None:
        return False

    for attr in attributes:
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


def flatten(nested_list):
    # フラットなリストとフリンジを用意
    flat_list = []
    fringe = [nested_list]
    while len(fringe) > 0:
        node = fringe.pop(0)
        # ノードがリストであれば子要素をフリンジに追加
        # リストでなければそのままフラットリストに追加
        if isinstance(node, list):
            fringe = node + fringe
        else:
            flat_list.append(node)

    return flat_list


# ジオメトリLineStringを結合し、MultiLineStringにする
def merge_linstrings(first, second):

    first_coordinates = []
    second_coordinates = []

    if first['geometry']['type'] == 'LineString':
        first_coordinates.extend(first['geometry']['coordinates'])
    else:
        first_coordinates = first['geometry']['coordinates']
    if second['geometry']['type'] == 'LineString':
        second_coordinates.extend(second['geometry']['coordinates'])
    else:
        second_coordinates = second['geometry']['coordinates']

    first_coordinates.extend(second_coordinates)
    return first_coordinates


# リンクを接合
def merge_links(a, b, node):
    # 新しいobjectid
    global new_id
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
        newc = merge_linstrings(b, a)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # -a-> n -b->  or <-b- n <-a- =>  keep
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc = merge_linstrings(a, b)
    # <-a- n <-b- => or -b-> n -a-> keep
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc = merge_linstrings(b, a)
    # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc = merge_linstrings(a, b)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]
    new_id = new_id + 1
    a['properties']['objectid'] = new_id
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['tonodeid'] = newtonodeid
    a['geometry']['coordinates'] = flatten(newc)
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


def remove_link(f, t, newlinks):
    return [x for x in newlinks if not x in (f, t)]


def find_cross_nodes():

    with fiona.open(link_file, "r") as fl:
        print('reading nodes and links')
        for feature in fl:
            all_nodes.append(feature['properties']['fromnodeid'])
            all_nodes.append(feature['properties']['tonodeid'])
            from_node_id = feature['properties']['fromnodeid']
            from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            to_node_id = feature['properties']['tonodeid']
            to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            all_link_count = all_link_count + 1

        # 2つのリンクが接続されているノードのobjectid属性を抽出
        c = collections.Counter(all_nodes)
        crossing_nodes = [k for k, v in c.items() if v == 2]
        return crossing_nodes

def make_lu(node_id):
    global cross_nodes, from_node_links, to_node_links, newlinks
    if node_id in cross_nodes:
        from_link, to_link = get_link(node_id, from_node_links, to_node_links)
        if check_attributes(from_link, to_link):
            newlinks = remove_link(from_link, to_link, newlinks)
            new_link = merge_links(from_link, to_link, node_id)
            new_from_node_id = new_link['properties']['fromnodeid']
            new_to_node_id = new_link['properties']['tonodeid']
            from_node_links[new_from_node_id] = new_link
            to_node_links[new_to_node_id] = new_link
            newlinks.append(new_link)
            return new_link


def process(inqueue, outqueue):

        for node in iter(inqueue.get, sentinel):
            outqueue.put(make_lu(node))
        outqueue.put(sentinel)


def write_file(path, queue):
    global meta
    with fiona.open(path, 'w', meta) as f:
        for line in iter(queue.get, sentinel):
            f.write(line)


def read_file(link_path, node_path, queue):
    global meta
    with fiona.open(link_path, "r") as fl:
        meta = fl.meta
        with fiona.open(node_path, "r") as fn:
            for v in fn:
                queue.put(v)
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
    global newlinks, from_node_links, to_node_links
    all_link_count = 0

    with fiona.open(link_path, "r") as fl:
        print('reading nodes and links')
        pickle_path = os.path.join(PICKLE_FILE_DIR, link_file + ".pickle")
        if os.path.exists(pickle_path):
            # キャッシュあれば読み込み
            print(f'Found pickle file ({os.path.basename(pickle_path)}). loading..')
            crossing_nodes, from_node_links, to_node_links = load_cache(pickle_path)
        else:
            for feature in fl:
                all_nodes.append(feature['properties']['fromnodeid'])
                all_nodes.append(feature['properties']['tonodeid'])
                from_node_id = feature['properties']['fromnodeid']
                from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
                to_node_id = feature['properties']['tonodeid']
                to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
                all_link_count = all_link_count + 1

            # 2つのリンクが接続されているノードのobjectid属性を抽出
            c = collections.Counter(all_nodes)
            crossing_nodes = [k for k, v in c.items() if v == 2]
            save_cache(pickle_path, (crossing_nodes, from_node_links, to_node_links))

        print('start threading')

        threading.Thread(target=read_file, args=(link_path, node_path, inq)).start()
        threading.Thread(target=process, args=(inq, outq)).start()
        write_file(new_link_path, outq)

    print(f"Finished.  All Links counts: {all_link_count}, Generated LUs: {merged_link_count}")


if __name__ == '__main__':
    start = time.time()
    # リンクレイヤからfromnodeid, tonodeid を取得し、Dict[objectid] 形式で辞書化　
    main()
    elapsed_time = time.time() - start
    print("elapsed_time: {:.3f}".format(elapsed_time) + "[sec]")

